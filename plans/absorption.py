"""First hitting probabilities on a weighted graph with absorbing boundaries."""

from collections import defaultdict, deque
from fractions import Fraction

from plans.linear import solve_linear


def hitting_probabilities(transitions, target):
    """Return hit mass for each input state. Missing rows end the walk.

    The input carries nonnegative edge weights with row sums at most one.
    Missing mass and exits other than the target contribute zero.
    """
    predecessors = defaultdict(list)
    for state, row in transitions.items():
        if state == target:
            continue
        for destination, weight in row.items():
            if weight > 0:
                predecessors[destination].append(state)
    reachable = {target}
    pending = deque([target])
    while pending:
        destination = pending.popleft()
        for state in predecessors[destination]:
            if state not in reachable:
                reachable.add(state)
                pending.append(state)

    # Each retained state has a positive path to the target. Closed classes
    # without such a path carry zero mass and are outside the linear system.
    active = [state for state in transitions if state in reachable and state != target]
    zero = Fraction(0)
    coefficients = []
    constants = []
    for state in active:
        row = transitions[state]
        coefficients.append([Fraction(state == other) - row.get(other, zero) for other in active])
        constants.append(row.get(target, zero))
    values = dict(zip(active, solve_linear(coefficients, constants), strict=True))
    return {
        state: Fraction(1) if state == target else values.get(state, zero)
        for state in transitions
    }
