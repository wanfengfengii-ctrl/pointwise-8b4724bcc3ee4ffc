"""Bind a request, compute exact review values, and submit for publication."""

from dataclasses import dataclass

from analysis.conditioning import conditional_probability
from analysis.release import release_probability
from analysis.route_event import joint_release_probability
from plans.catalog import load_plan
from plans.snapshot import FixedPlan
from reports.publish import issue_report
from reports.receipt import FormalReport, ReportCandidate


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    plan_id: int
    start: str
    handoff: tuple[str, str]


class InvalidReviewRequest(ValueError):
    pass


def validate_review_request(plan: FixedPlan, request: ReviewRequest):
    if plan.plan_id != request.plan_id:
        raise InvalidReviewRequest('request and plan identities differ')
    if type(request.start) is not str or request.start not in plan.stations:
        raise InvalidReviewRequest('start is not a public station on this plan')
    handoff = request.handoff
    if not isinstance(handoff, (tuple, list)) or len(handoff) != 2:
        raise InvalidReviewRequest('give two ordered public handoff endpoints')
    if any(type(endpoint) is not str or endpoint not in plan.stations for endpoint in handoff):
        raise InvalidReviewRequest('handoff endpoints must be public on this plan')
    return ReviewRequest(plan.plan_id, request.start, tuple(handoff))


def publish_report(archive, plan_id, start, handoff, *, before_commit=None) -> FormalReport:
    plan = load_plan(archive, plan_id)
    request = validate_review_request(plan, ReviewRequest(plan_id, start, handoff))
    release = release_probability(plan, request.start)
    joint = joint_release_probability(plan, request.start, request.handoff)
    candidate = ReportCandidate(
        plan.plan_id, request.start, request.handoff, release,
        conditional_probability(release, joint),
    )
    return issue_report(archive, candidate, before_commit=before_commit)
