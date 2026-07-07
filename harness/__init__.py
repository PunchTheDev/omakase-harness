"""The mutable harness package — the artifact OC-H miners evolve.

Contract (locked, enforced by eval_adapter.py): expose
    run_task(router, task, pool, run_seed, split, budget) -> oc_eval.engine.TaskResult
The router is opaque (the pinned OC-R champion); workers are reachable only
through `pool`. Budgets are enforced by the caller regardless of what this
code does — blowing them forfeits the task.
"""
from .system import run_task

__all__ = ["run_task"]
