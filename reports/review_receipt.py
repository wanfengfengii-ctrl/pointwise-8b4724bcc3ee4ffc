"""Two-stage review report data, identity, receipt, and payload encoding."""

import json
from dataclasses import dataclass
from fractions import Fraction

REVIEW_REPORT_VERSION = 2


@dataclass(frozen=True, slots=True)
class ReviewReportCandidate:
    plan_id: int
    revision_id: int
    start: str
    handoff: tuple[str, str]
    handoff_release_probability: Fraction
    review_completion_given_handoff_release: Fraction | None


@dataclass(frozen=True, slots=True)
class ReviewReceipt:
    report_id: int
    plan_id: int


@dataclass(frozen=True, slots=True)
class FormalReviewReport:
    receipt: ReviewReceipt
    revision_id: int
    start: str
    handoff: tuple[str, str]
    handoff_release_probability: Fraction
    review_completion_given_handoff_release: Fraction | None

    @property
    def report_id(self):
        return self.receipt.report_id

    @property
    def plan_id(self):
        return self.receipt.plan_id


def validate_review_candidate(candidate):
    if type(candidate.plan_id) is not int or not 0 < candidate.plan_id < 2**63:
        raise ValueError('invalid plan number')
    if type(candidate.revision_id) is not int or not 0 < candidate.revision_id < 2**63:
        raise ValueError('invalid revision number')
    if type(candidate.start) is not str or not candidate.start.strip():
        raise ValueError('report start is required')
    if type(candidate.handoff) is not tuple or len(candidate.handoff) != 2 or any(
        type(endpoint) is not str or not endpoint.strip() for endpoint in candidate.handoff
    ):
        raise ValueError('report requires an ordered handoff pair')
    denominator = candidate.handoff_release_probability
    conditional = candidate.review_completion_given_handoff_release
    if type(denominator) is not Fraction or not 0 <= denominator <= 1:
        raise ValueError('invalid handoff release probability')
    if denominator == 0:
        if conditional is not None:
            raise ValueError('an empty handoff subgroup requires a None completion ratio')
    elif type(conditional) is not Fraction or not 0 <= conditional <= 1:
        raise ValueError('a nonempty handoff subgroup requires an exact completion ratio')


def _encode_fraction(value):
    if value is None:
        return None
    return [format(value.numerator, 'x'), format(value.denominator, 'x')]


def _decode_fraction(value):
    if value is None:
        return None
    numerator, denominator = value
    return Fraction(int(numerator, 16), int(denominator, 16))


def encode_review_report(candidate):
    body = {
        'version': REVIEW_REPORT_VERSION,
        'revision_id': candidate.revision_id,
        'start': candidate.start,
        'handoff': list(candidate.handoff),
        'handoff_release': _encode_fraction(candidate.handoff_release_probability),
        'review_completion': _encode_fraction(
            candidate.review_completion_given_handoff_release
        ),
    }
    return json.dumps(body, ensure_ascii=False, separators=(',', ':'))


def decode_review_report(report_id, plan_id, payload):
    body = json.loads(payload)
    return FormalReviewReport(
        ReviewReceipt(report_id, plan_id), body['revision_id'], body['start'],
        tuple(body['handoff']), _decode_fraction(body['handoff_release']),
        _decode_fraction(body['review_completion']),
    )
