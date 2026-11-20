"""Exact solution of square systems with one right-hand side."""

from fractions import Fraction


class SingularSystem(ValueError):
    pass


def solve_linear(coefficients, constants):
    size = len(coefficients)
    if len(constants) != size or any(len(row) != size for row in coefficients):
        raise ValueError('expected a square system with a matching right-hand side')
    matrix = [
        [*(Fraction(value) for value in row), Fraction(rhs)]
        for row, rhs in zip(coefficients, constants, strict=True)
    ]
    for column in range(size):
        pivot = next((i for i in range(column, size) if matrix[i][column]), None)
        if pivot is None:
            raise SingularSystem(f'no pivot in column {column}')
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        pivot_row = matrix[column]
        divisor = pivot_row[column]
        for index in range(column, size + 1):
            pivot_row[index] /= divisor
        for index in range(column + 1, size):
            row = matrix[index]
            factor = row[column]
            if factor:
                for entry in range(column, size + 1):
                    row[entry] -= factor * pivot_row[entry]
    solution = [Fraction(0)] * size
    for index in range(size - 1, -1, -1):
        row = matrix[index]
        solution[index] = row[-1] - sum(
            row[column] * solution[column] for column in range(index + 1, size)
        )
    return tuple(solution)


def solve_linear_systems(coefficients, right_hand_sides):
    """Solve several systems sharing one square matrix exactly.

    Each entry of ``right_hand_sides`` is one constant column. The result is a
    tuple of solution columns in the same order. States from which no
    right-hand-side mass is reachable (rows that only feed closed classes) are
    removed from the elimination and keep an exact zero solution.
    """
    size = len(coefficients)
    width = len(right_hand_sides)
    if width == 0:
        return ()
    if any(len(row) != size for row in coefficients) or any(
        len(rhs) != size for rhs in right_hand_sides
    ):
        raise ValueError('expected a square matrix with matching right-hand sides')
    matrix = [[Fraction(value) for value in row] for row in coefficients]
    rhs = [[Fraction(column[row]) for column in right_hand_sides] for row in range(size)]
    # States that can feed a nonzero constant through off-diagonal edges are
    # the only ones that can carry nonzero solutions. Everything else is dead.
    driven = {row for row in range(size) if any(column[row] != 0 for column in right_hand_sides)}
    reachable = set(driven)
    pending = list(driven)
    while pending:
        target = pending.pop()
        for row in range(size):
            if row not in reachable and matrix[row][target] != 0 and row != target:
                reachable.add(row)
                pending.append(row)
    dead = [row not in reachable for row in range(size)]
    for row in range(size):
        if dead[row]:
            matrix[row] = [Fraction(0)] * size
            matrix[row][row] = Fraction(1)
            rhs[row] = [Fraction(0)] * width
    for column in range(size):
        if dead[column]:
            continue
        pivot = next((i for i in range(column, size)
                      if not dead[i] and matrix[i][column] != 0), None)
        if pivot is None:
            # Defensive fallback: an unreachable row keeps zero mass.
            dead[column] = True
            matrix[column] = [Fraction(0)] * size
            matrix[column][column] = Fraction(1)
            rhs[column] = [Fraction(0)] * width
            continue
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        rhs[column], rhs[pivot] = rhs[pivot], rhs[column]
        divisor = matrix[column][column]
        for index in range(column, size):
            matrix[column][index] /= divisor
        rhs[column] = [value / divisor for value in rhs[column]]
        for index in range(column + 1, size):
            if dead[index]:
                continue
            factor = matrix[index][column]
            if factor:
                for entry in range(column, size):
                    matrix[index][entry] -= factor * matrix[column][entry]
                rhs[index] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(rhs[index], rhs[column], strict=True)
                ]
    solutions = [[Fraction(0)] * size for _ in range(width)]
    for index in range(size - 1, -1, -1):
        if dead[index]:
            continue
        for k in range(width):
            tail_k = sum(
                matrix[index][column] * solutions[k][column]
                for column in range(index + 1, size)
            )
            solutions[k][index] = rhs[index][k] - tail_k
    return tuple(tuple(column) for column in solutions)


def solve_sparse_systems(sparse_rows, right_hand_sides):
    """Solve sparse square systems sharing one matrix, exactly.

    ``sparse_rows[row]`` maps a column index to its nonzero coefficient; the
    diagonal is expected to be present. Rows unable to feed any right-hand
    side carry an exact zero solution. Rows are stored as dictionaries so the
    cost follows the number of nonzeros rather than the matrix dimension.
    """
    size = len(sparse_rows)
    width = len(right_hand_sides)
    if width == 0:
        return ()
    rows = [dict(sparse_rows[row]) for row in range(size)]
    rhs = [[Fraction(column[row]) for column in right_hand_sides] for row in range(size)]

    driven = {
        row for row in range(size)
        if any(column[row] != 0 for column in right_hand_sides)
    }
    predecessors = [[] for _ in range(size)]
    for row, entries in enumerate(rows):
        for column in entries:
            if column != row:
                predecessors[column].append(row)
    reachable = set(driven)
    pending = list(driven)
    while pending:
        target = pending.pop()
        for row in predecessors[target]:
            if row not in reachable:
                reachable.add(row)
                pending.append(row)
    dead = [row not in reachable for row in range(size)]
    for row in range(size):
        if dead[row]:
            rows[row] = {row: Fraction(1)}
            rhs[row] = [Fraction(0)] * width

    for column in range(size):
        if dead[column]:
            continue
        pivot = next(
            (row for row in range(column, size)
             if not dead[row] and column in rows[row] and rows[row][column] != 0),
            None,
        )
        if pivot is None:
            dead[column] = True
            rows[column] = {column: Fraction(1)}
            rhs[column] = [Fraction(0)] * width
            continue
        if pivot != column:
            rows[column], rows[pivot] = rows[pivot], rows[column]
            rhs[column], rhs[pivot] = rhs[pivot], rhs[column]
        pivot_entries = rows[column]
        divisor = pivot_entries[column]
        for entry in list(pivot_entries):
            pivot_entries[entry] /= divisor
        rhs[column] = [value / divisor for value in rhs[column]]
        for row in range(column + 1, size):
            if dead[row] or column not in rows[row]:
                continue
            entries = rows[row]
            factor = entries.pop(column)
            for entry, value in pivot_entries.items():
                if entry == column:
                    continue
                updated = entries.get(entry, Fraction(0)) - factor * value
                if updated:
                    entries[entry] = updated
                elif entry in entries:
                    del entries[entry]
            rhs[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(rhs[row], rhs[column], strict=True)
            ]

    solutions = [[Fraction(0)] * size for _ in range(width)]
    for row in range(size - 1, -1, -1):
        if dead[row]:
            continue
        entries = rows[row]
        for k in range(width):
            tail = sum(
                value * solutions[k][column]
                for column, value in entries.items()
                if column > row
            )
            solutions[k][row] = rhs[row][k] - tail
    return tuple(tuple(column) for column in solutions)
