"""Validate each declared next outcome from the current public position."""

from plans.snapshot import PlanOutcome
from walks.result import complete_walk
from walks.trace import WalkTrace


class InvalidWalk(ValueError):
    pass


class WalkSession:
    def __init__(self, plan, start):
        if type(start) is not str or start not in plan.stations:
            raise InvalidWalk('start is not a public station on this plan')
        self._plan = plan
        self._current = start
        self._trace = WalkTrace(start)
        self._terminal = None
        self._rejected = False

    def _reject(self, reason):
        self._rejected = True
        raise InvalidWalk(reason)

    def advance(self, outcome):
        if self._rejected or self._terminal is not None:
            self._reject('the session cannot accept a further step')
        if type(outcome) is not str and not isinstance(outcome, PlanOutcome):
            self._reject('give a station name or a PlanOutcome')
        if self._plan.row_for(self._current).get(outcome, 0) <= 0:
            self._reject(f'impossible step from {self._current} to {outcome!r}')
        if isinstance(outcome, PlanOutcome):
            self._terminal = outcome
        else:
            self._current = outcome
            self._trace.record_arrival(outcome)

    def finish(self):
        if self._rejected or self._terminal is None:
            self._reject('the walk has no valid terminal outcome')
        return complete_walk(self._plan.plan_id, self._trace, self._terminal)
