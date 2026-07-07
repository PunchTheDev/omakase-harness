"""Seed harness: the OC-R reference engine, verbatim.

This is deliberately the zero-improvement baseline — main's score with this
file IS the bar. Improve routing follow-ups, verification, retries, memory,
decomposition; keep the contract in __init__.py.
"""
from __future__ import annotations

from oc_eval import engine, suites
from oc_eval.workers import Pool


def run_task(router, task: suites.Task, pool: Pool, run_seed: int, split: str,
             budget: engine.Budget = engine.Budget()) -> engine.TaskResult:
    return engine.run_task(router, task, pool, run_seed, split, budget)
