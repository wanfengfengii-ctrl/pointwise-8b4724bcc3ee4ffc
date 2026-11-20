"""Replay a supplied complete shop-floor record against one plan."""

from plans.catalog import load_plan
from walks.result import WalkResult
from walks.session import InvalidWalk, WalkSession


def replay_walk(archive, plan_id, start, outcomes) -> WalkResult:
    plan = load_plan(archive, plan_id)
    session = WalkSession(plan, start)
    try:
        steps = iter(outcomes)
    except TypeError as error:
        raise InvalidWalk('outcomes must be an iterable of steps') from error
    for outcome in steps:
        session.advance(outcome)
    return session.finish()
