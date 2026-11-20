"""Retrieve the original formal report and receipt by report number."""

from reports.receipt import decode_report
from reports.storage import load_report_row


class ReportNotFound(LookupError):
    pass


def read_report(archive, report_id):
    row = load_report_row(archive, report_id)
    if row is None:
        raise ReportNotFound(report_id)
    return decode_report(*row)
