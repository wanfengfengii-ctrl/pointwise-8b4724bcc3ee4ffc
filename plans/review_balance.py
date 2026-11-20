"""Audit complete, ordered review rows before freezing a V2 plan."""

from fractions import Fraction

from plans.review_snapshot import PHASES, review_outcome_keys
from plans.snapshot import PlanOutcome


class InvalidReviewPlan(ValueError):
    pass


def validate_review_ledger(stations, rows):
    if not 1 <= len(stations) <= 6 or len(set(stations)) != len(stations):
        raise InvalidReviewPlan('invalid public station list')
    if len(rows) != len(stations):
        raise InvalidReviewPlan('review rows do not match the public stations')
    canonical = review_outcome_keys(stations)
    for station, station_rows in zip(stations, rows, strict=True):
        if len(station_rows) != len(PHASES):
            raise InvalidReviewPlan(f'missing entry-phase rows at {station}')
        for phase, values in zip(PHASES, station_rows, strict=True):
            if len(values) != len(canonical):
                raise InvalidReviewPlan(f'invalid outcome columns at {station} phase {phase}')
            if any(type(value) is not Fraction or not 0 <= value <= 1 for value in values):
                raise InvalidReviewPlan(f'invalid probability at {station} phase {phase}')
            if sum(values) != 1:
                raise InvalidReviewPlan(f'probability does not balance at {station} phase {phase}')
    never_key = (PlanOutcome.NEVER, None)
    if canonical[-1] != never_key:
        raise InvalidReviewPlan('the retention column must close each review row')
