"""Exact review data, report identity, and receipt encoding."""

import json
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class ReportCandidate:
    plan_id: int
    start: str
    handoff: tuple[str, str]
    release_probability: Fraction
    retention_given_release: Fraction | None


@dataclass(frozen=True, slots=True)
class Receipt:
    report_id: int
    plan_id: int


@dataclass(frozen=True, slots=True)
class FormalReport:
    receipt: Receipt
    start: str
    handoff: tuple[str, str]
    release_probability: Fraction
    retention_given_release: Fraction | None

    @property
    def report_id(self):
        return self.receipt.report_id

    @property
    def plan_id(self):
        return self.receipt.plan_id


def validate_candidate(candidate):
    if type(candidate.plan_id) is not int or not 0 < candidate.plan_id < 2**63:
        raise ValueError('invalid plan number')
    if type(candidate.start) is not str or not candidate.start.strip():
        raise ValueError('report start is required')
    if type(candidate.handoff) is not tuple or len(candidate.handoff) != 2 or any(
        type(endpoint) is not str or not endpoint.strip() for endpoint in candidate.handoff
    ):
        raise ValueError('report requires an ordered handoff pair')
    release = candidate.release_probability
    conditional = candidate.retention_given_release
    if type(release) is not Fraction or not 0 <= release <= 1:
        raise ValueError('invalid release probability')
    if release == 0:
        if conditional is not None:
            raise ValueError('zero release requires an empty conditional value')
    elif type(conditional) is not Fraction or not 0 <= conditional <= 1:
        raise ValueError('positive release requires an exact conditional probability')


def _encode_fraction(value):
    if value is None:
        return None
    return [format(value.numerator, 'x'), format(value.denominator, 'x')]


def _decode_fraction(value):
    if value is None:
        return None
    numerator, denominator = value
    return Fraction(int(numerator, 16), int(denominator, 16))


def encode_report(candidate):
    body = {
        'start': candidate.start,
        'handoff': candidate.handoff,
        'release': _encode_fraction(candidate.release_probability),
        'conditional': _encode_fraction(candidate.retention_given_release),
    }
    return json.dumps(body, ensure_ascii=False, separators=(',', ':'))


def decode_report(report_id, plan_id, payload):
    body = json.loads(payload)
    return FormalReport(
        Receipt(report_id, plan_id), body['start'], tuple(body['handoff']),
        _decode_fraction(body['release']), _decode_fraction(body['conditional']),
    )
