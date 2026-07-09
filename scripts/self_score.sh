#!/usr/bin/env bash
# Self-score the current harness/ against main's baseline — the same
# king-of-the-hill judgment the canonical rerun applies. Boots a throwaway mock pool.
set -euo pipefail
cd "$(dirname "$0")/.."
EVAL=../omakase-eval
PY=$EVAL/.venv/bin/python
[ -x "$PY" ] || PY=python3

$PY -m omakase_eval.cli mockpool --port 8100 & POOL_PID=$!
trap 'kill $POOL_PID 2>/dev/null' EXIT
sleep 0.3

[ -f runs/main-baseline.json ] || {
  echo "no main baseline — computing one from the seed harness (maintainer does this on merge)"
  git stash -q --include-untracked -- harness/ 2>/dev/null || true
  $PY eval_adapter.py --pool $EVAL/configs/pool.dev.json --rebaseline
  git stash pop -q 2>/dev/null || true
}

$PY eval_adapter.py --pool $EVAL/configs/pool.dev.json "$@"
