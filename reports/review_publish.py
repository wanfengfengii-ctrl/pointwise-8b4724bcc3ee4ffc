"""Stage and commit one review report and its handover entry as a unit."""

from reports.review_receipt import (
    FormalReviewReport,
    ReviewReceipt,
    encode_review_report,
    validate_review_candidate,
)
from reports.storage import insert_handover_entry, insert_report, publication_transaction


class PublishError(RuntimeError):
    pass


def issue_review_report(archive, candidate, *, before_commit=None):
    validate_review_candidate(candidate)
    payload = encode_review_report(candidate)
    try:
        with publication_transaction(archive):
            report_id = insert_report(archive, candidate.plan_id, payload)
            insert_handover_entry(archive, report_id, candidate.plan_id, candidate.start)
            receipt = ReviewReceipt(report_id, candidate.plan_id)
            report = FormalReviewReport(
                receipt, candidate.revision_id, candidate.start, candidate.handoff,
                candidate.handoff_release_probability,
                candidate.review_completion_given_handoff_release,
            )
            if before_commit is not None:
                before_commit(receipt)
    except Exception as error:
        raise PublishError(f'publication failed for plan {candidate.plan_id}') from error
    return report
