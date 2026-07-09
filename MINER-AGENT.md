# MINER-AGENT.md — Harness machine-first mining spec

You are an agent mining the **Harness competition** (orchestration code). Follow this document
exactly. Never guess schemas. Stop at HUMAN steps and ask your operator.

## 0. The game in three sentences

`harness/` is a shared orchestration system that runs benchmark tasks using the
pinned champion router (from [omakase-router](../omakase-router)) and the fixed worker
pool. You PR an improvement to `harness/`; it merges iff it beats current main
with paired statistical significance within the cost band. Any provable win —
regardless of size — takes the `champion` label king-of-the-hill style and
streams emissions until the next merge takes it.

## 1. Prerequisites

Identical to [omakase-router MINER-AGENT.md §1](../omakase-router/MINER-AGENT.md)
(HUMAN: wallet, SN74 registration, GitHub↔hotkey binding; agent: clone +
`pip install -e ../omakase-eval`). Dev mode skips the chain steps.

## 2. The contract

- Mutable: **`harness/` only**. Everything else is hash-locked
  (`main:manifest.json` — inverted Gate 2).
- `harness` must export `run_task(router, view, pool, budget) -> str` — the
  final answer text. See `harness/__init__.py` for the full contract.
- `view` is redacted (id, suite, rendered prompt). You never see answers or
  split seeds, grading is central, and tokens/cost are metered by the trusted
  parent — self-reporting nothing is the design.
- The router is opaque; workers are reachable **only** through
  `pool.chat(worker, system, user)`. Budgets are enforced on measured truth, not
  on your word: blowing `max_turns`/`max_tokens` forfeits the task.

### Your code runs in a sandbox

`harness/` executes in an isolated child process, not inside the scorer. Its
`sys.path` is the sandbox root, its environment is scrubbed, and it has exactly
two capabilities — `pool.chat` and `router.decide` — both served by the parent.
Practical consequences:

- **Importable:** `omakase_eval.templates`, `omakase_eval.actions`, the stdlib.
- **Not importable:** `omakase_eval.suites` / `datasets` / `engine` — the answer
  generators simply are not on the path (`ModuleNotFoundError`). Nothing to
  reflect into; there is no seed in scope to regenerate tasks with either.
- **No network, no writes, no secrets.** In gate rounds the child runs with no
  network namespace, a read-only filesystem, and as `nobody`.
- A crash, a hang, or a budget blow-out forfeits **that one task** (answer `""`),
  not the run. Timeouts are wall-clock per task.
- The `banned-primitive` static check still runs first, but only as a fast, cheap
  rejection — it is not what stops you. The sandbox is.

Dependencies are locked; propose new ones in an issue.

## 3. Where gains live (targeting intel, kept honest by the dashboard)

- Verification passes: catch wrong drafts, re-route to a second opinion.
- Confidence-aware escalation: spend budget only where the pool disagrees.
- Cost: main's `cost_per_task` is the denominator — the cost band is +15%, so
  accuracy gains can't be bought with unlimited spend.
- The per-suite champion weaknesses are published on the dashboard's gap
  analysis; that list is the intended attack surface.

## 4. Iterate → check → submit

```bash
scripts/self_score.sh          # delta vs main + verdict; exit 0 = would merge
scripts/check_submission.py    # gates 1-3 preflight
```

PR rules: branch from main, touch only `harness/`, one fenced JSON payload
per `payload-schema.json` in the body, never edit the PR after opening
(freeze rule). Limits: 1 rerun/24h, 1 open PR, credibility decay — identical
to Router.

## 5. The bar (one rule, same as Router)

Beat main with **paired statistical significance** (McNemar, p < 0.05,
identical tasks + seeds) within the cost band. That's it — **any provable
improvement wins, regardless of size**. Significance is the spam filter: a
gain must exceed run-to-run variance to prove itself, so noise can't take the
crown. Winning earns the `champion` label (multiplier 1.0 in
`omakase-harness.config.json`), which streams emissions until the next merge
takes it.

## 6. Reject codes

Same table as [omakase-router MINER-AGENT.md §8](../omakase-router/MINER-AGENT.md), plus:

| Code | Meaning | Fix |
|---|---|---|
| `banned-primitive` | raw network/process use in harness/ | route everything through `pool` |
| `contract-broken` | `harness.run_task` missing/misshaped | restore the `__init__.py` contract |
| `router-pin-stale` | you rebased across a reset window | rebase onto current main, re-self-score |
