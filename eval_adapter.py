#!/usr/bin/env python3
"""Locked scoring adapter for OC-H.

Runs the mutable harness/ package over a split with the pinned champion router,
pairs the result against main's stored baseline vector, and emits a delta-tier
verdict. Miners cannot change this file (inverted Gate 2: here the harness is
mutable and the eval surface is locked).

Usage:
    python eval_adapter.py --pool ../oc-eval/configs/pool.dev.json \
        [--rebaseline] [--out runs/run.json] [--frontier runs/frontier.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "oc-eval"))
sys.path.insert(0, ROOT)

from oc_eval import engine, frontier, routers, score, stats, suites  # noqa: E402
from oc_eval.workers import Pool  # noqa: E402

import harness  # noqa: E402 — the mutable package under test

BASELINE_PATH = os.path.join(ROOT, "runs", "main-baseline.json")

# Delta tiers: label -> (min accuracy delta, gittensor label multiplier)
TIERS = [("breakthrough", 0.08, 2.0), ("major-delta", 0.03, 1.0), ("minor-delta", 0.0, 0.3)]
COST_TOLERANCE = 1.15


def load_pinned_router() -> routers.TinyRouter:
    with open(os.path.join(ROOT, "router-pin.json")) as f:
        pin = json.load(f)
    path = os.path.join(ROOT, "pinned", "router-weights.json")
    if routers.sha256_file(path) != pin["weights_sha256"]:
        raise SystemExit("pinned router weights do not match router-pin.json")
    return routers.TinyRouter.load(path)


def run_harness(pool: Pool, split: str, seed: int) -> list[engine.TaskResult]:
    router = load_pinned_router()
    tasks = suites.generate_split(split, seed)
    budget = engine.Budget()
    return [harness.run_task(router, t, pool, seed, split, budget) for t in tasks]


def tier_for(delta: float, significant: bool) -> str | None:
    if not significant:
        return None
    return next((label for label, floor, _ in TIERS if delta >= floor), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rebaseline", action="store_true",
                    help="store this run as main's baseline (maintainer, post-merge/reset only)")
    ap.add_argument("--out")
    ap.add_argument("--frontier")
    args = ap.parse_args()

    pool = Pool.from_config(args.pool)
    results = run_harness(pool, args.split, args.seed)
    axes = score.axes(results)
    vector = score.correctness_vector(results)

    if args.rebaseline:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w") as f:
            json.dump({"split": args.split, "seed": args.seed, "vector": vector,
                       "axes": axes.__dict__}, f)
        print(f"main baseline stored: accuracy {axes.accuracy:.3f}")
        return 0

    with open(BASELINE_PATH) as f:
        base = json.load(f)
    if (base["split"], base["seed"]) != (args.split, args.seed):
        raise SystemExit("baseline was computed for a different (split, seed)")

    cmp_ = stats.compare(vector, [bool(x) for x in base["vector"]])
    cost_ok = axes.cost_per_task <= base["axes"]["cost_per_task"] * COST_TOLERANCE
    tier = tier_for(cmp_.delta, cmp_.significant and cost_ok)

    blob = {
        "competition": "oc-harness",
        "split": args.split, "seed": args.seed, "n_tasks": len(vector),
        "accuracy": round(axes.accuracy, 4), "baseline_accuracy": round(base["axes"]["accuracy"], 4),
        "delta": round(cmp_.delta, 4), "p_value": round(cmp_.p_value, 6),
        "cost_per_task": round(axes.cost_per_task, 4), "cost_ok": cost_ok,
        "tier": tier, "passed": tier is not None,
    }
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(blob, f, indent=1)
    if args.frontier:
        frontier.append(args.frontier, "run", blob)

    print(f"accuracy {blob['accuracy']} vs main {blob['baseline_accuracy']} "
          f"(Δ {blob['delta']:+}, p={blob['p_value']}) cost_ok={cost_ok}")
    print(f"verdict: {'PASS — tier ' + tier if tier else 'FAIL — no significant in-band gain'}")
    return 0 if tier else 1


if __name__ == "__main__":
    raise SystemExit(main())
