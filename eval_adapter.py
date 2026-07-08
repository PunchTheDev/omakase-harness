#!/usr/bin/env python3
"""Locked scoring adapter for Harness (contract v2).

The mutable harness never sees answers and never grades itself:
- it receives a redacted TaskView (id, suite, rendered prompt) — no answer, no
  options object, no split seed, so answers are not reconstructible;
- all worker calls go through a metered, budget-enforcing pool wrapper that
  injects eval metadata itself — tokens/cost/latency are measured here, not
  self-reported;
- the harness returns only its final answer string; grading is central.

Usage:
    python eval_adapter.py --pool ../omakase-eval/configs/pool.dev.json \
        [--per-suite 150] [--rebaseline] [--out runs/run.json] [--frontier runs/frontier.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.abspath(__file__))
# Bind omakase_eval BEFORE the miner's repo root is importable, so a miner-added
# omakase_eval/ package in harness/ cannot shadow the real scoring modules.
sys.path.insert(0, os.path.join(ROOT, "..", "omakase-eval"))
from omakase_eval import frontier, routers, score, stats, suites, transcripts  # noqa: E402
from omakase_eval.engine import Budget, Step, TaskResult  # noqa: E402
from omakase_eval.actions import Call  # noqa: E402
from omakase_eval.workers import Pool  # noqa: E402

sys.path.append(ROOT)  # appended, not inserted — miner files never win a name race
import harness  # noqa: E402 — the mutable package under test

BASELINE_PATH = os.path.join(ROOT, "runs", "main-baseline.json")

# Delta tiers: label -> (min accuracy delta, gittensor label multiplier)
TIERS = [("breakthrough", 0.08, 2.0), ("major-delta", 0.03, 1.0), ("minor-delta", 0.0, 0.3)]
COST_TOLERANCE = 1.15


@dataclass(frozen=True)
class TaskView:
    """What the harness is allowed to know about a task."""

    id: str
    suite: str
    prompt: str


class BudgetExceeded(Exception):
    pass


@dataclass
class ScopedPool:
    """Metered pool facade: injects metadata, enforces budgets, records ground truth."""

    inner: Pool
    budget: Budget
    _meta: dict = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0

    @property
    def workers(self):
        return self.inner.workers

    def begin(self, task_id: str, split: str, seed: int) -> None:
        self._meta = {"split": split, "seed": seed, "task_id": task_id}
        self.steps, self.tokens, self.cost, self.latency_ms = [], 0, 0.0, 0.0

    def chat(self, worker: str, system: str, user: str):
        if len(self.steps) >= self.budget.max_turns or self.tokens >= self.budget.max_tokens:
            raise BudgetExceeded
        c = self.inner.chat(worker, system, user, metadata=self._meta)
        self.steps.append(Step(Call(worker), c.text, c.tokens))
        self.tokens += c.tokens
        self.cost += c.cost
        self.latency_ms += c.latency_ms
        return c


def load_pinned_router() -> routers.TinyRouter:
    with open(os.path.join(ROOT, "router-pin.json")) as f:
        pin = json.load(f)
    path = os.path.join(ROOT, "pinned", "router-weights.json")
    if routers.sha256_file(path) != pin["weights_sha256"]:
        raise SystemExit("pinned router weights do not match router-pin.json")
    return routers.TinyRouter.load(path)


def run_harness(pool: Pool, split: str, seed: int, per_suite: int) -> list[TaskResult]:
    router = load_pinned_router()
    budget = Budget()
    scoped = ScopedPool(pool, budget)
    results = []
    for task in suites.generate_split(split, seed, per_suite):
        view = TaskView(task.id, task.suite, suites.render_prompt(task, seed))
        scoped.begin(task.id, split, seed)
        try:
            answer = harness.run_task(router, view, scoped, budget)
        except BudgetExceeded:
            answer = ""  # budget blown = forfeited task
        except Exception:  # noqa: BLE001 — a crashing harness forfeits, never crashes the eval
            answer = ""
        results.append(TaskResult(
            task.id, task.suite,
            correct=bool(answer) and suites.grade(task, str(answer), seed),
            tokens=scoped.tokens, cost=scoped.cost, latency_ms=scoped.latency_ms,
            steps=scoped.steps, answer=str(answer),
        ))
    return results


def tier_for(delta: float, significant: bool) -> str | None:
    if not significant:
        return None
    return next((label for label, floor, _ in TIERS if delta >= floor), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--per-suite", type=int, default=40, help="tasks per suite; gate splits use more than dev")
    ap.add_argument("--rebaseline", action="store_true",
                    help="store this run as main's baseline (maintainer, post-merge/reset only)")
    ap.add_argument("--out")
    ap.add_argument("--frontier")
    ap.add_argument("--transcripts", help="dir for the content-addressed per-task transcript")
    args = ap.parse_args()

    pool = Pool.from_config(args.pool)
    tasks = suites.generate_split(args.split, args.seed, args.per_suite)
    results = run_harness(pool, args.split, args.seed, args.per_suite)
    axes = score.axes(results)
    vector = score.correctness_vector(results)

    if args.rebaseline:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w") as f:
            json.dump({"split": args.split, "seed": args.seed, "per_suite": args.per_suite,
                       "vector": vector, "axes": axes.__dict__}, f)
        print(f"main baseline stored: accuracy {axes.accuracy:.3f}")
        return 0

    with open(BASELINE_PATH) as f:
        base = json.load(f)
    if (base["split"], base["seed"], base.get("per_suite", 40)) != (args.split, args.seed, args.per_suite):
        raise SystemExit("baseline was computed for a different (split, seed, per_suite)")

    cmp_ = stats.compare(vector, [bool(x) for x in base["vector"]])
    cost_ok = axes.cost_per_task <= base["axes"]["cost_per_task"] * COST_TOLERANCE
    tier = tier_for(cmp_.delta, cmp_.significant and cost_ok)

    blob = {
        "competition": "omakase-harness",
        "split": args.split, "seed": args.seed, "n_tasks": len(vector),
        "accuracy": round(axes.accuracy, 4), "baseline_accuracy": round(base["axes"]["accuracy"], 4),
        "delta": round(cmp_.delta, 4), "p_value": round(cmp_.p_value, 6),
        "cost_per_task": round(axes.cost_per_task, 4), "cost_ok": cost_ok,
        "tier": tier, "passed": tier is not None,
    }
    tx = transcripts.build(tasks, results, args.seed,
                           header={"competition": "omakase-harness", "split": args.split, "seed": args.seed})
    tx_dir = args.transcripts or (os.path.join(os.path.dirname(args.out), "transcripts") if args.out else "runs/transcripts")
    blob["transcript_sha256"] = transcripts.write(tx, tx_dir)
    task_summary = transcripts.summarize(tx)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump({**blob, "task_summary": task_summary}, f, indent=1)
    if args.frontier:
        frontier.append(args.frontier, "run", blob)

    print(f"accuracy {blob['accuracy']} vs main {blob['baseline_accuracy']} "
          f"(Δ {blob['delta']:+}, p={blob['p_value']}) cost_ok={cost_ok}")
    print(f"verdict: {'PASS — tier ' + tier if tier else 'FAIL — no significant in-band gain'}")
    return 0 if tier else 1


if __name__ == "__main__":
    raise SystemExit(main())
