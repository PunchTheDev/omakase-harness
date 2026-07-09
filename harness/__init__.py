"""The mutable harness package — the artifact Harness miners evolve.

Contract v2 (locked, enforced by eval_adapter.py): expose
    run_task(router, view, pool, budget) -> str   # the final answer text

This package runs inside `omakase_eval.sandbox`'s isolated child process, so the
guarantees below are structural rather than promises:

- `view` is a redacted TaskView (id, suite, rendered prompt). Answers, options
  objects, and split seeds are never visible and not reconstructible here: the
  generators are not importable and the seed is not in this process.
- `pool.chat(worker, system, user)` is the ONLY way to reach workers. It is an
  RPC to the trusted parent, which meters it and enforces the budget on measured
  truth — blow the budget and the task is forfeited.
- Grading is central: whatever string you return is graded against the hidden
  answer by the parent. Returning anything else scores zero.
- Importable here: the stdlib, `omakase_eval.templates`, `omakase_eval.actions`.
  A crash forfeits one task, never the run.
"""
from .system import run_task

__all__ = ["run_task"]
