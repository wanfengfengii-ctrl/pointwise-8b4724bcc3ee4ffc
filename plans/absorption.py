"""First-hit probabilities and multi-target absorption on weighted graphs."""

from collections import defaultdict, deque
from fractions import Fraction

from plans.linear import solve_linear, solve_linear_systems

_ZERO = Fraction(0)
_ONE = Fraction(1)


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


def absorption_distributions(transitions, seeds, targets):
    """Return ``{seed: {target: probability}}`` for absorbing target tokens.

    Transient states are the keys of ``transitions``. An edge whose
    destination is one of the targets ends the walk; edges to states outside
    the transition table and any closed transient classes without an exit
    contribute zero to every target.
    """
    target_set = set(targets)
    predecessors = defaultdict(list)
    for state, row in transitions.items():
        if state in target_set:
            continue
        for destination, weight in row.items():
            if weight > 0:
                predecessors[destination].append(state)
    reachable = set(target_set)
    pending = deque(target_set)
    while pending:
        destination = pending.popleft()
        for state in predecessors[destination]:
            if state not in reachable:
                reachable.add(state)
                pending.append(state)
    active = [state for state in transitions if state in reachable and state not in target_set]
    index = {state: position for position, state in enumerate(active)}
    size = len(active)
    matrix = [[_ZERO] * size for _ in range(size)]
    rhs_columns = [[_ZERO] * size for _ in targets]
    for position, state in enumerate(active):
        matrix[position][position] = _ONE
        row = transitions[state]
        for destination, weight in row.items():
            if destination in target_set:
                target_position = targets.index(destination)
                rhs_columns[target_position][position] += weight
            elif destination in index:
                matrix[position][index[destination]] -= weight
    solved = solve_linear_systems(matrix, rhs_columns) if active else ()
    solutions = {
        state: tuple(column[position] for column in solved)
        for position, state in enumerate(active)
    }
    results = {}
    for seed in seeds:
        if seed in solutions:
            values = solutions[seed]
        else:
            values = tuple(
                _ONE if seed == target else _ZERO for target in targets
            )
        results[seed] = dict(zip(targets, values, strict=True))
    return results
