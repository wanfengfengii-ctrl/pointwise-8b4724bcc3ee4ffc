"""Retrieve the original formal report and receipt by report number."""

import json

from reports.receipt import decode_report
from reports.review_receipt import REVIEW_REPORT_VERSION, decode_review_report
from reports.storage import load_report_row


class ReportNotFound(LookupError):
    pass


def read_report(archive, report_id):
    row = load_report_row(archive, report_id)
    if row is None:
        raise ReportNotFound(report_id)
    report_id_value, plan_id, payload = row
    body = json.loads(payload)
    if isinstance(body, dict) and body.get('version') == REVIEW_REPORT_VERSION:
        return decode_review_report(report_id_value, plan_id, payload)
    return decode_report(report_id_value, plan_id, payload)
