import random
import unittest
from fractions import Fraction

from plans.linear import (
    SingularSystem,
    solve_linear,
    solve_linear_systems,
    solve_sparse_systems,
)


class TestLinearSolvers(unittest.TestCase):
    def test_single_rhs_basic_system(self):
        coefficients = [[Fraction(2), Fraction(1)], [Fraction(1), Fraction(3)]]
        constants = [Fraction(1), Fraction(2)]
        solution = solve_linear(coefficients, constants)
        self.assertEqual(
            solution, (Fraction(1, 5), Fraction(3, 5))
        )

    def test_singular_system_is_flagged(self):
        with self.assertRaises(SingularSystem):
            solve_linear(
                [[Fraction(1), Fraction(-1)], [Fraction(-1), Fraction(1)]],
                [Fraction(1), Fraction(1)],
            )

    def test_multi_rhs_matches_single_rhs(self):
        random.seed(11)
        for size in range(1, 8):
            for _ in range(25):
                matrix = [
                    [Fraction(random.randint(-3, 3), random.randint(1, 4))
                     for _ in range(size)]
                    for _ in range(size)
                ]
                for row in range(size):
                    matrix[row][row] = (
                        sum((abs(matrix[row][col]) for col in range(size)), Fraction(0))
                        + Fraction(random.randint(1, 3))
                    )
                right_hand_sides = [
                    [Fraction(random.randint(-2, 2), random.randint(1, 3))
                     for _ in range(size)]
                    for _ in range(3)
                ]
                expected = tuple(
                    solve_linear(matrix, rhs) for rhs in right_hand_sides
                )
                self.assertEqual(
                    solve_linear_systems(matrix, right_hand_sides), expected
                )

    def test_sparse_matches_dense_including_dead_states(self):
        random.seed(23)
        for size in (1, 2, 4, 7, 12):
            for trial in range(30):
                dense = [[Fraction(0)] * size for _ in range(size)]
                for row in range(size):
                    for col in random.sample(range(size), random.randint(1, min(size, 4))):
                        dense[row][col] = Fraction(
                            random.randint(-2, 2), random.randint(1, 3)
                        )
                    dense[row][row] = (
                        sum((abs(dense[row][col]) for col in range(size)), Fraction(0))
                        + Fraction(random.randint(1, 3))
                    )
                if size > 3 and trial % 6 == 0:
                    # A closed class with no driving constant stays at zero.
                    dense[0] = [Fraction(0)] * size
                    dense[0][0] = Fraction(1)
                right_hand_sides = [
                    [Fraction(random.randint(-2, 2), random.randint(1, 3))
                     for _ in range(size)]
                    for _ in range(2)
                ]
                sparse = [
                    {col: value for col, value in enumerate(row) if value != 0}
                    for row in dense
                ]
                self.assertEqual(
                    solve_sparse_systems(sparse, right_hand_sides),
                    solve_linear_systems(dense, right_hand_sides),
                )

    def test_sparse_empty_right_hand_sides(self):
        self.assertEqual(solve_sparse_systems([{0: Fraction(1)}], []), ())


if __name__ == '__main__':
    unittest.main()
