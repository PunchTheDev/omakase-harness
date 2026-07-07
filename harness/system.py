"""Hedge-aware retry harness (contract v2).

The reference flow takes the router's first answer at face value. Workers,
like real models, hedge when unsure ("possibly: …") — a free confidence
signal. A hedged draft triggers one second-opinion call; hedges are rare, so
cost stays in band.
"""
from __future__ import annotations

from oc_eval import templates
from oc_eval.actions import Call

HEDGE = "possibly"
SECOND_OPINION = "generalist-mock"  # broadest solo profile in the pinned pool


def _ask(pool, worker: str, prompt: str, draft: str | None = None) -> str:
    role = "worker"
    return pool.chat(worker, templates.SYSTEM[role], templates.user_message(role, prompt, draft)).text


def run_task(router, view, pool, budget) -> str:
    action = router.decide(task=view, prompt=view.prompt, steps=[])
    if not isinstance(action, Call):
        return ""  # a router that won't route forfeits
    answer = _ask(pool, action.worker, view.prompt)

    if HEDGE in answer.lower():
        second = SECOND_OPINION if SECOND_OPINION != action.worker else next(
            w for w in pool.workers if w != action.worker)
        retry = _ask(pool, second, view.prompt, draft=answer)
        if HEDGE not in retry.lower():
            answer = retry  # confident second opinion beats a hedged draft

    return answer
