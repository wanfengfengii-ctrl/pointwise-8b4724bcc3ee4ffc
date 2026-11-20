"""Stage and commit one report and its handover entry as a unit."""

from reports.receipt import FormalReport, Receipt, encode_report, validate_candidate
from reports.storage import insert_handover_entry, insert_report, publication_transaction


class PublishError(RuntimeError):
    pass


def issue_report(archive, candidate, *, before_commit=None):
    validate_candidate(candidate)
    payload = encode_report(candidate)
    try:
        with publication_transaction(archive):
            report_id = insert_report(archive, candidate.plan_id, payload)
            insert_handover_entry(archive, report_id, candidate.plan_id, candidate.start)
            receipt = Receipt(report_id, candidate.plan_id)
            report = FormalReport(
                receipt, candidate.start, candidate.handoff, candidate.release_probability,
                candidate.retention_given_release,
            )
            if before_commit is not None:
                before_commit(receipt)
    except Exception as error:
        raise PublishError(f'publication failed for plan {candidate.plan_id}') from error
    return report
