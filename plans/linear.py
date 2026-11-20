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
