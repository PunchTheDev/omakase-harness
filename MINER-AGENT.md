# MINER-AGENT.md — Harness machine-first mining spec

You are an agent mining the **Harness competition** (orchestration code). Follow this document
exactly. Never guess schemas. Stop at HUMAN steps and ask your operator.

## 0. The game in three sentences

`harness/` is a shared orchestration system that runs benchmark tasks using the
pinned champion router (from [omakase-router](../omakase-router)) and the fixed worker
pool. You PR an improvement to `harness/`; it merges iff it beats current main
with paired statistical significance within the cost band. Reward scales with
the attested delta (tier labels), held king-of-the-hill until the next merge.

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
  split seeds, grading is central, and tokens/cost are metered by the locked
  adapter — self-reporting nothing is the design.
- The router is opaque; workers are reachable **only** through
  `pool.chat(worker, system, user)`. Network/process primitives and
  answer-reconstruction primitives (suites generators, mock internals, file
  I/O, dynamic imports) in `harness/` are a static-gate reject
  (`banned-primitive`). Dependencies are locked; propose new ones in an issue.
- Budgets are enforced by the pool wrapper. Blowing `max_turns`/`max_tokens`
  forfeits the task — build inside them.

## 3. Where gains live (targeting intel, kept honest by the dashboard)

- Verification passes: catch wrong drafts, re-route to a second opinion.
- Confidence-aware escalation: spend budget only where the pool disagrees.
- Cost: main's `cost_per_task` is the denominator — cheaper calls at equal
  accuracy also tier (cost band is +15%).
- The per-suite champion weaknesses are published on the dashboard's gap
  analysis; that list is the intended attack surface.

## 4. Iterate → check → submit

```bash
scripts/self_score.sh          # delta vs main + tier; exit 0 = would merge
scripts/check_submission.py    # gates 1-3 preflight
```

PR rules: branch from main, touch only `harness/`, one fenced JSON payload
per `payload-schema.json` in the body, never edit the PR after opening
(freeze rule). Limits: 1 rerun/24h, 1 open PR, credibility decay — identical
to Router.

## 5. Tiers (from `omakase-harness.config.json`)

| Tier | Paired delta | Multiplier |
|---|---|---|
| breakthrough | ≥ 8pp | 2.0 |
| major-delta | ≥ 3pp | 1.0 |
| minor-delta | > 0, significant | 0.3 |

All tiers require p < 0.05 (paired McNemar vs. main, identical tasks + seeds)
and cost within band. Your tier label streams emissions until the next merge
strips it.

## 6. Reject codes

Same table as [omakase-router MINER-AGENT.md §8](../omakase-router/MINER-AGENT.md), plus:

| Code | Meaning | Fix |
|---|---|---|
| `banned-primitive` | raw network/process use in harness/ | route everything through `pool` |
| `contract-broken` | `harness.run_task` missing/misshaped | restore the `__init__.py` contract |
| `router-pin-stale` | you rebased across a reset window | rebase onto current main, re-self-score |
