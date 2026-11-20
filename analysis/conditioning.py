"""Check that the handoff event is contained in release before conditioning."""

from fractions import Fraction


class InvalidProbabilityMass(ValueError):
    pass


def conditional_probability(release: Fraction, joint: Fraction) -> Fraction | None:
    if not 0 <= joint <= release <= 1:
        raise InvalidProbabilityMass('joint release mass must lie within total release mass')
    return joint / release if release else None
