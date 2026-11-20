"""Joint release mass for a handoff retained in the final erased route."""

from fractions import Fraction
from functools import cache

from plans.absorption import hitting_probabilities
from plans.snapshot import FixedPlan, PlanOutcome


def joint_release_probability(plan: FixedPlan, start: str, handoff: tuple[str, str]) -> Fraction:
    rows = {station: plan.row_for(station) for station in plan.stations}
    zero = Fraction(0)

    @cache
    def return_mass(current, forbidden):
        # After the last departure of each earlier station, touching any of
        # them would invalidate this prefix. Dropped transitions keep zero
        # return mass, so the remaining rows keep their original weights.
        allowed = tuple(station for station in plan.stations if station not in forbidden)
        transitions = {
            station: {destination: rows[station][destination] for destination in allowed}
            for station in allowed if station != current
        }
        probabilities = hitting_probabilities(transitions, current)
        row = rows[current]
        return row[current] + sum(row[station] * mass for station, mass in probabilities.items())

    def visit(current, forbidden, mass, contains_handoff):
        returns = return_mass(current, forbidden)
        if returns == 1:
            return zero
        # Excursions that return to this station are erased. Sum their
        # geometric weight before the final departure or release.
        mass /= 1 - returns
        row = rows[current]
        joint = mass * row[PlanOutcome.RELEASE] if contains_handoff else zero
        next_forbidden = forbidden | {current}
        for destination in plan.stations:
            if destination not in next_forbidden and row[destination] > 0:
                joint += visit(
                    destination, next_forbidden, mass * row[destination],
                    contains_handoff or (current, destination) == handoff,
                )
        return joint

    return visit(start, frozenset(), Fraction(1), False)
