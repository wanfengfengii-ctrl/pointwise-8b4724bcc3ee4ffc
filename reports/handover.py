"""List successful publications for a plan in signing order."""

from dataclasses import dataclass

from plans.catalog import load_plan
from reports.storage import list_handover_rows


@dataclass(frozen=True, slots=True)
class HandoverEntry:
    report_id: int
    start: str


def handover(archive, plan_id):
    plan = load_plan(archive, plan_id)
    return [HandoverEntry(report_id, start) for report_id, start in list_handover_rows(archive, plan.plan_id)]
