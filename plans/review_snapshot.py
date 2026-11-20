"""Frozen two-stage review plans: joint outcome and next-phase probabilities."""

import json
from dataclasses import dataclass
from fractions import Fraction

from plans.snapshot import PlanOutcome

REVIEW_PLAN_VERSION = 2
PHASES = (0, 1, 2)


def review_outcome_keys(stations):
    """Canonical (outcome, next_phase) key order for one entry-phase row."""
    keys = []
    for station in stations:
        for phase in PHASES:
            keys.append((station, phase))
    for terminal in (PlanOutcome.RELEASE, PlanOutcome.REJECT):
        for phase in PHASES:
            keys.append((terminal, phase))
    keys.append((PlanOutcome.NEVER, None))
    return tuple(keys)


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    plan_id: int
    revision_id: int
    stations: tuple[str, ...]
    # rows[station_index][entry_phase] is the mapping in canonical key order.
    rows: tuple[tuple[tuple[Fraction, ...], ...], ...]

    @property
    def plan_version(self):
        return REVIEW_PLAN_VERSION

    def row_for(self, station, phase):
        if type(station) is not str or station not in self.stations:
            raise KeyError(station)
        if phase not in PHASES:
            raise ValueError('review phases are 0 (unreviewed), 1 (rechecked), 2 (complete)')
        station_index = self.stations.index(station)
        return dict(zip(review_outcome_keys(self.stations), self.rows[station_index][phase], strict=True))


def _encode_key(key):
    outcome, next_phase = key
    if outcome is PlanOutcome.NEVER:
        return ['n']
    if isinstance(outcome, PlanOutcome):
        return ['t', outcome.value, next_phase]
    return ['s', outcome, next_phase]


def _decode_key(body):
    kind = body[0]
    if kind == 'n':
        return PlanOutcome.NEVER, None
    if kind == 't':
        return PlanOutcome(body[1]), body[2]
    return body[1], body[2]


def _encode_fraction(value):
    return [format(value.numerator, 'x'), format(value.denominator, 'x')]


def _decode_fraction(body):
    return Fraction(int(body[0], 16), int(body[1], 16))


def encode_review_plan(stations, rows):
    payload = {
        'version': REVIEW_PLAN_VERSION,
        'stations': stations,
        'review_rows': [
            [
                [
                    [_encode_key(key), _encode_fraction(value)]
                    for key, value in zip(review_outcome_keys(stations), phase_row, strict=True)
                ]
                for phase_row in station_rows
            ]
            for station_rows in rows
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def decode_review_plan(plan_id, revision_id, payload):
    body = json.loads(payload)
    stations = tuple(body['stations'])
    canonical = review_outcome_keys(stations)
    rows = []
    for station_entry in body['review_rows']:
        phase_rows = []
        for phase_entry in station_entry:
            mapping = {_decode_key(key): _decode_fraction(value) for key, value in phase_entry}
            if tuple(mapping) != canonical:
                raise ValueError('review plan payload is missing canonical outcome keys')
            phase_rows.append(tuple(mapping[key] for key in canonical))
        rows.append(tuple(phase_rows))
    return ReviewPlan(plan_id, revision_id, stations, tuple(rows))
