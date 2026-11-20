"""Completed, immutable walk evidence."""

from dataclasses import dataclass

from plans.snapshot import PlanOutcome
from walks.trace import WalkTrace


@dataclass(frozen=True, slots=True)
class WalkResult:
    plan_id: int
    actual: tuple[str, ...]
    retained: tuple[str, ...]
    erasures: tuple[tuple[str, tuple[str, ...]], ...]
    terminal: PlanOutcome

    @property
    def retained_handoffs(self):
        return tuple(zip(self.retained, self.retained[1:]))


def complete_walk(plan_id, trace: WalkTrace, terminal: PlanOutcome):
    if not isinstance(terminal, PlanOutcome):
        raise ValueError('a completed walk requires a terminal outcome')
    snapshot = trace.snapshot()
    return WalkResult(plan_id, snapshot.actual, snapshot.retained, snapshot.erasures, terminal)
