# omakase-harness — the Harness orchestration-system competition

One shared harness, continuously improved. PR a change to `harness/` that
beats main on the benchmark with paired significance; any provable win takes
the crown and streams emissions until the next merge takes it.

- **Humans:** read [omakase-router's quickstart](../omakase-router/docs/quickstart.md),
  then [MINER-AGENT.md](MINER-AGENT.md) §2–5 for what differs here.
- **Agents:** [MINER-AGENT.md](MINER-AGENT.md).
- **Docs** (how-it-works, trust, rules): shared with [omakase-router/docs](../omakase-router/docs)
  — one trust model, two competitions. Harness-specific rules live in
  [MINER-AGENT.md](MINER-AGENT.md) and [omakase-harness.config.json](omakase-harness.config.json).

```bash
scripts/self_score.sh          # Δ vs main + verdict; exit 0 = would merge
scripts/check_submission.py    # gates 1-3 preflight
```

The pinned Router champion (`router-pin.json`) is the fixed brain; this repo is
the evolving body. Pin bumps land only in Monday reset windows.
