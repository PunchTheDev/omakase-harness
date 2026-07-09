#!/usr/bin/env python3
"""Locked scoring adapter for Harness (contract v2).

This process is TRUSTED: it holds the tasks, the answers, the seed and the pool
credentials. The mutable harness never runs here — it runs in an isolated child
(`omakase_eval.sandbox`) that has no answer modules on its path, no seed in its
environment, and no capability but two RPCs back to us. Consequences:

- it cannot grade itself (grading happens here, after the child returns a string);
- it cannot reconstruct answers (no generators, no seed);
- it cannot self-report cost (tokens/cost/latency are measured here, on the
  real pool calls the child asked for);
- it cannot exceed budget (checked here, on measured truth).

Usage:
    python eval_adapter.py --pool ../omakase-eval/configs/pool.dev.json \
        [--per-suite 150] [--rebaseline] [--out runs/run.json] [--sandbox docker]

The gate seed is read from $OMAKASE_SEED when set (never passed on argv, where
`ps` would leak it); --seed is for the public dev split only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
# Bind omakase_eval BEFORE the miner's repo root is importable, so a miner-added
# omakase_eval/ package in harness/ cannot shadow the real scoring modules.
sys.path.insert(0, os.path.join(ROOT, "..", "omakase-eval"))
from omakase_eval import frontier, routers, sandbox, score, stats, suites, transcripts  # noqa: E402
from omakase_eval.engine import Budget  # noqa: E402
from omakase_eval.workers import Pool  # noqa: E402

BASELINE_PATH = os.path.join(ROOT, "runs", "main-baseline.json")
HARNESS_DIR = os.path.join(ROOT, "harness")

COST_TOLERANCE = 1.15
PUBLIC_SPLIT = "dev"  # the only split whose seed and transcripts may be published


def load_pinned_router() -> routers.TinyRouter:
    with open(os.path.join(ROOT, "router-pin.json")) as f:
        pin = json.load(f)
    path = os.path.join(ROOT, "pinned", "router-weights.json")
    if routers.sha256_file(path) != pin["weights_sha256"]:
        raise SystemExit("pinned router weights do not match router-pin.json")
    return routers.TinyRouter.load(path)


def resolve_seed(args) -> int:
    """Gate seeds come from the environment; only the public dev seed may be argv."""
    env_seed = os.environ.get("OMAKASE_SEED")
    if env_seed:
        return int(env_seed)
    if args.split != PUBLIC_SPLIT:
        raise SystemExit(
            f"split {args.split!r} is a private split: its seed must come from $OMAKASE_SEED, "
            "never argv (visible in `ps`) and never a committed config."
        )
    return args.seed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--seed", type=int, default=1, help="public dev seed; private splits use $OMAKASE_SEED")
    ap.add_argument("--per-suite", type=int, default=40, help="tasks per suite; gate splits use more than dev")
    ap.add_argument("--rebaseline", action="store_true",
                    help="store this run as main's baseline (maintainer, post-merge/reset only)")
    ap.add_argument("--out")
    ap.add_argument("--frontier")
    ap.add_argument("--transcripts", help="dir for the content-addressed per-task transcript")
    ap.add_argument("--sandbox", default="process", choices=("process", "docker"),
                    help="isolation for the untrusted harness; docker adds no-network + read-only FS")
    ap.add_argument("--sandbox-timeout", type=float, default=60.0, help="wall-clock seconds per task")
    args = ap.parse_args()

    seed = resolve_seed(args)
    public = args.split == PUBLIC_SPLIT

    pool = Pool.from_config(args.pool)
    tasks = suites.generate_split(args.split, seed, args.per_suite)
    cfg = sandbox.SandboxConfig(mode=args.sandbox, per_task_timeout_s=args.sandbox_timeout)
    results, forfeits = sandbox.run_harness_split(
        HARNESS_DIR, load_pinned_router(), tasks, pool, seed, args.split, Budget(), cfg)
    if forfeits:
        print(f"{len(forfeits)} task(s) forfeited: {'; '.join(forfeits[:3])}"
              + (" …" if len(forfeits) > 3 else ""), file=sys.stderr)

    axes = score.axes(results)
    vector = score.correctness_vector(results)
    fingerprint = suites.split_fingerprint(args.split, seed)

    if args.rebaseline:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w") as f:
            # The seed is committed only for the public split; every split records
            # a fingerprint so a stale baseline is caught without leaking the seed.
            json.dump({"split": args.split, "seed": seed if public else None,
                       "seed_fingerprint": fingerprint, "per_suite": args.per_suite,
                       "vector": vector, "axes": axes.__dict__}, f)
        print(f"main baseline stored: accuracy {axes.accuracy:.3f}")
        return 0

    with open(BASELINE_PATH) as f:
        base = json.load(f)
    if (base["split"], base.get("per_suite", 40)) != (args.split, args.per_suite):
        raise SystemExit("baseline was computed for a different (split, per_suite)")
    if base.get("seed_fingerprint") != fingerprint:
        raise SystemExit(
            "baseline was computed for a different seed (fingerprint mismatch) — "
            "the split rotated; rerun with --rebaseline on the trusted host first."
        )

    # King-of-the-hill, same rule as Router: ANY positive delta with paired
    # significance (in cost band) wins — significance IS the spam filter, since
    # a gain must exceed run-to-run variance to prove itself. No size tiers.
    cmp_ = stats.compare(vector, [bool(x) for x in base["vector"]])
    cost_ok = axes.cost_per_task <= base["axes"]["cost_per_task"] * COST_TOLERANCE
    passed = cmp_.significant and cmp_.delta > 0 and cost_ok

    blob = {
        "competition": "omakase-harness",
        "split": args.split, "n_tasks": len(vector),
        "accuracy": round(axes.accuracy, 4), "baseline_accuracy": round(base["axes"]["accuracy"], 4),
        "delta": round(cmp_.delta, 4), "p_value": round(cmp_.p_value, 6),
        "cost_per_task": round(axes.cost_per_task, 4), "cost_ok": cost_ok,
        "passed": passed,
    }
    if public:  # a private split's seed is never written to a published blob
        blob["seed"] = seed

    header = {"competition": "omakase-harness", "split": args.split}
    if public:
        header["seed"] = seed
    tx = transcripts.build(tasks, results, seed, header=header)
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
    print(f"verdict: {'PASS — would take the crown' if passed else 'FAIL — no significant in-band gain'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
