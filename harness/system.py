"""Hedge-aware retry harness.

The reference engine takes the router's first answer at face value. Workers,
like real models, hedge when unsure ("possibly: …") — a free confidence
signal. This harness detects a hedged draft and spends one extra call on a
second opinion, keeping cost within band because hedges are rare.
"""
from __future__ import annotations

from oc_eval import suites, templates
from oc_eval.actions import Call
from oc_eval.engine import Budget, Step, TaskResult
from oc_eval.workers import Pool

HEDGE = "possibly"
SECOND_OPINION = "generalist-mock"  # broadest solo profile in the pinned pool


def _call(result: TaskResult, pool: Pool, action: Call, prompt: str, metadata: dict, draft: str | None) -> str:
    c = pool.chat(action.worker, templates.SYSTEM[action.role],
                  templates.user_message(action.role, prompt, draft), metadata)
    result.steps.append(Step(action, c.text, c.tokens))
    result.tokens += c.tokens
    result.cost += c.cost
    result.latency_ms += c.latency_ms
    return c.text


def run_task(router, task: suites.Task, pool: Pool, run_seed: int, split: str,
             budget: Budget = Budget()) -> TaskResult:
    result = TaskResult(task.id, task.suite, correct=False)
    prompt = suites.render_prompt(task, run_seed)
    metadata = {"split": split, "seed": run_seed, "task_id": task.id}

    action = router.decide(task=task, prompt=prompt, steps=result.steps)
    if not isinstance(action, Call):
        return result  # a router that won't route forfeits
    answer = _call(result, pool, action, prompt, metadata, None)

    if HEDGE in answer.lower() and result.tokens < budget.max_tokens:
        second = SECOND_OPINION if SECOND_OPINION != action.worker else next(
            w for w in pool.workers if w != action.worker)
        retry = _call(result, pool, Call(second), prompt, metadata, answer)
        if HEDGE not in retry.lower():
            answer = retry  # confident second opinion beats a hedged draft

    result.answer = answer
    result.correct = suites.grade(task, answer, run_seed)
    return result
