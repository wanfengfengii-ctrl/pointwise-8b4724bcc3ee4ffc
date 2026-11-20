"""Exact handoff-release and review-completion mass for a V2 review plan.

The public route follows the V1 erasure rule: returning to an already
retained public station drops the suffix after that station. Review phases
are separate state that survives erasure; every actual arrival already had
its label effect frozen into the plan's ``next_phase`` columns.

The full retained route together with the phase in effect at its last
station is a Markov state, so every scenario is solved exactly as one
absorbing linear system over those states. Reject, retention, and permanent
cycles contribute no release mass, matching the original
transfer-probability accounting.
"""

from fractions import Fraction

from plans.linear import solve_sparse_systems
from plans.review_snapshot import PHASES, ReviewPlan
from plans.snapshot import PlanOutcome

_ZERO = Fraction(0)
_ONE = Fraction(1)


def _candidate_states(plan: ReviewPlan, start: str):
    """Every simple path beginning at the start, paired with each phase."""
    states = []
    routes = [(start,)]
    while routes:
        route = routes.pop()
        for phase in PHASES:
            states.append((route, phase))
        used = set(route)
        for station in plan.stations:
            if station not in used:
                routes.append((*route, station))
    return states


def review_handoff_mass(plan: ReviewPlan, start: str, handoff: tuple[str, str]):
    """Joint release mass that retains the handoff, split by review completion.

    Returns ``(handoff_release, completed_release)`` where the second value is
    the portion of the first that releases in the terminal's completed phase.
    """
    states = _candidate_states(plan, start)
    index = {state: position for position, state in enumerate(states)}
    size = len(states)
    sparse_rows = [{} for _ in range(size)]
    handoff_rhs = [_ZERO] * size
    complete_rhs = [_ZERO] * size

    for position, (route, phase) in enumerate(states):
        entries = sparse_rows[position]
        entries[position] = _ONE
        current = route[-1]
        for (outcome, next_phase), weight in plan.row_for(current, phase).items():
            if weight == 0:
                continue
            if outcome is PlanOutcome.RELEASE:
                if handoff in tuple(zip(route, route[1:])):
                    handoff_rhs[position] += weight
                    # Completion is the terminal phase carried by release.
                    if next_phase == 2:
                        complete_rhs[position] += weight
            elif isinstance(outcome, PlanOutcome):
                # Reject and retention never contribute release mass.
                continue
            else:
                next_route = (
                    route[: route.index(outcome) + 1]
                    if outcome in route
                    else (*route, outcome)
                )
                target = (next_route, next_phase)
                if target in index:
                    target_index = index[target]
                    entries[target_index] = entries.get(target_index, _ZERO) - weight
                # A target outside the candidate table is a permanent public
                # cycle without an observable release; it keeps zero mass.

    handoff_values, complete_values = solve_sparse_systems(
        sparse_rows, [handoff_rhs, complete_rhs]
    )
    start_index = index[((start,), 0)]
    return handoff_values[start_index], complete_values[start_index]
