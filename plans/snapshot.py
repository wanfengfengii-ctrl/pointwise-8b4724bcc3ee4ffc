"""The public transfer snapshot exchanged with walks and review."""

import json
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction


class PlanOutcome(Enum):
    RELEASE = 'release'
    REJECT = 'reject'
    NEVER = 'never'


@dataclass(frozen=True, slots=True)
class FixedPlan:
    plan_id: int
    revision_id: int
    stations: tuple[str, ...]
    rows: tuple[tuple[Fraction, ...], ...]

    @property
    def outcomes(self):
        return (*self.stations, *PlanOutcome)

    def row_for(self, station):
        try:
            index = self.stations.index(station)
        except ValueError as error:
            raise KeyError(station) from error
        return dict(zip(self.outcomes, self.rows[index], strict=True))


def encode_plan(stations, rows):
    body = {
        'stations': stations,
        'rows': [
            [[format(value.numerator, 'x'), format(value.denominator, 'x')]
             for value in row]
            for row in rows
        ],
    }
    return json.dumps(body, ensure_ascii=False, separators=(',', ':'))


def decode_plan(plan_id, revision_id, payload):
    body = json.loads(payload)
    rows = tuple(
        tuple(Fraction(int(numerator, 16), int(denominator, 16)) for numerator, denominator in row)
        for row in body['rows']
    )
    return FixedPlan(plan_id, revision_id, tuple(body['stations']), rows)
