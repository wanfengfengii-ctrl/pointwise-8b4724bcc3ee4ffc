"""Bind a V2 review request, compute exact values, and submit the report."""

from analysis.conditioning import conditional_probability
from analysis.review_route import review_handoff_mass
from plans.catalog import load_plan
from plans.review_snapshot import ReviewPlan
from reports.review_publish import issue_review_report
from reports.review_receipt import ReviewReportCandidate


class InvalidReviewRequest(ValueError):
    pass


def _validate(plan, plan_id, start, handoff):
    if not isinstance(plan, ReviewPlan):
        raise InvalidReviewRequest('review publication requires a V2 review plan')
    if plan.plan_id != plan_id:
        raise InvalidReviewRequest('request and plan identities differ')
    if type(start) is not str or start not in plan.stations:
        raise InvalidReviewRequest('start is not a public station on this plan')
    if not isinstance(handoff, (tuple, list)) or len(handoff) != 2:
        raise InvalidReviewRequest('give two ordered public handoff endpoints')
    endpoints = tuple(handoff)
    if any(type(endpoint) is not str or endpoint not in plan.stations for endpoint in endpoints):
        raise InvalidReviewRequest('handoff endpoints must be public on this plan')
    return endpoints


def publish_review_report(archive, plan_id, start, handoff, *, before_commit=None):
    plan = load_plan(archive, plan_id)
    if not isinstance(plan, ReviewPlan):
        # A missing plan number keeps its V1 lookup error; an existing V1 plan
        # is a wrong-version request.
        raise InvalidReviewRequest(f'plan {plan_id} is not a V2 review plan')
    handoff = _validate(plan, plan_id, start, handoff)
    denominator, completed = review_handoff_mass(plan, start, handoff)
    ratio = conditional_probability(denominator, completed)
    candidate = ReviewReportCandidate(
        plan.plan_id, plan.revision_id, start, handoff, denominator, ratio,
    )
    return issue_review_report(archive, candidate, before_commit=before_commit)
