"""Total eventual release mass under a selected fixed transfer plan."""

from fractions import Fraction

from plans.absorption import hitting_probabilities
from plans.snapshot import FixedPlan, PlanOutcome


def release_probability(plan: FixedPlan, start: str) -> Fraction:
    transitions = {station: plan.row_for(station) for station in plan.stations}
    return hitting_probabilities(transitions, PlanOutcome.RELEASE)[start]
