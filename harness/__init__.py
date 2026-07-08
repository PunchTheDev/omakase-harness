"""The mutable harness package — the artifact Harness miners evolve.

Contract v2 (locked, enforced by eval_adapter.py): expose
    run_task(router, view, pool, budget) -> str   # the final answer text

- `view` is a redacted TaskView (id, suite, rendered prompt). Answers, options
  objects, and split seeds are never visible and not reconstructible here.
- `pool.chat(worker, system, user)` is the ONLY way to reach workers; it is
  metered and budget-enforced centrally — blow the budget and the task is
  forfeited. Tokens/cost/latency are measured by the adapter, never trusted.
- Grading is central: whatever string you return is graded against the hidden
  answer by the locked adapter. Returning anything else scores zero.
"""
from .system import run_task

__all__ = ["run_task"]
