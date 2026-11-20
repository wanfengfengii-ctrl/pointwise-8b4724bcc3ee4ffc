"""Sample bench counts for two-stage review, with a V1 comparison."""

import json
from contextlib import closing
from fractions import Fraction

from analysis.request import publish_report
from analysis.review_request import publish_review_report
from plans.freeze import freeze_plan
from plans.freeze_review import freeze_review_plan
from reports.history import read_report
from reports.storage import open_archive
from source.corrections import amend
from source.intake import receive
from source.revisions import Station, TransferCount
from source.storage import open_source


RESET_ON_RETURN = {
    "batch": "CY-review-order",
    "stations": (("A", True), ("B", True), ("C", True), ("P", False), ("Q", False), ("R", False)),
    "release": "pass",
    "reject": "fail",
    "counts": (("A", "P", 1), ("P", "Q", 1), ("Q", "B", 1), ("B", "pass", 1),
               ("B", "C", 1), ("C", "R", 1), ("R", "B", 1)),
    "labels": {"P": "recheck", "Q": "witness", "R": "reset"},
    "replacements": (("A", "P", 0), ("A", "Q", 1), ("P", "Q", 0), ("P", "B", 1),
                     ("Q", "B", 0), ("Q", "P", 1)),
    "label_only_patch": {"R": None},
}

PAIRED_EXIT = {
    "batch": "CY-review-fork",
    "stations": (("A", True), ("B", True), ("C", True), ("P", False), ("Q", False), ("X", False)),
    "release": "pass",
    "reject": "fail",
    "counts": (("A", "P", 1), ("A", "X", 1), ("P", "B", 1), ("X", "C", 1),
               ("B", "Q", 1), ("C", "Q", 1), ("Q", "pass", 1)),
    "labels": {"P": "recheck", "Q": "witness"},
    "replacements": (("P", "B", 0), ("P", "C", 1), ("X", "C", 0), ("X", "B", 1)),
}


def compare_v1(case, expected_retention):
    with closing(open_archive(":memory:")) as archive:
        with closing(open_source(":memory:")) as source:
            original = receive(
                source, case["batch"], [Station(*row) for row in case["stations"]],
                case["release"], case["reject"], [TransferCount(*row) for row in case["counts"]],
            )
            changed = amend(source, original, [TransferCount(*row) for row in case["replacements"]])
            plans = [freeze_plan(source, archive, revision) for revision in (original, changed)]
        assert plans[0].revision_id != plans[1].revision_id
        assert plans[0].stations == plans[1].stations and plans[0].rows == plans[1].rows
        reports = [publish_report(archive, plan.plan_id, "A", ("A", "B")) for plan in plans]
        for report in reports:
            assert report.release_probability == Fraction(1)
            assert report.retention_given_release == expected_retention
            assert read_report(archive, report.report_id) == report
        erased = None
        if case is RESET_ON_RETURN:
            report = publish_report(archive, plans[0].plan_id, "A", ("B", "C"))
            erased = report.retention_given_release
            assert erased == Fraction(0)
        return {
            "batch": case["batch"],
            "revisions": [original, changed],
            "same_v1_rows": True,
            "v1_release": [str(report.release_probability) for report in reports],
            "v1_retention": [str(report.retention_given_release) for report in reports],
            "v1_erased_handoff": None if erased is None else str(erased),
        }


def compare_v2(case):
    """Freeze labeled V2 plans and sign the exact review completion ratios."""
    with closing(open_archive(":memory:")) as archive:
        with closing(open_source(":memory:")) as source:
            original = receive(
                source, case["batch"] + "-v2", [Station(*row) for row in case["stations"]],
                case["release"], case["reject"],
                [TransferCount(*row) for row in case["counts"]], labels=case["labels"],
            )
            original_plan = freeze_review_plan(source, archive, original)
            swapped = amend(
                source, original,
                [TransferCount(*row) for row in case["replacements"]],
            )
            swapped_plan = freeze_review_plan(source, archive, swapped)
            label_revision = amend(
                source, original, [], labels=case.get("label_only_patch", {})
            )
            label_plan = freeze_review_plan(source, archive, label_revision)

        def pair(plan):
            report = publish_review_report(archive, plan.plan_id, "A", ("A", "B"))
            assert read_report(archive, report.report_id) == report
            return [
                str(report.handoff_release_probability),
                None if report.review_completion_given_handoff_release is None
                else str(report.review_completion_given_handoff_release),
            ]

        erased = None
        if case is RESET_ON_RETURN:
            erased_report = publish_review_report(
                archive, original_plan.plan_id, "B", ("B", "C")
            )
            erased = [
                str(erased_report.handoff_release_probability),
                erased_report.review_completion_given_handoff_release,
            ]
        return {
            "batch": case["batch"],
            "review_rows_balance": all(
                sum(original_plan.row_for(station, phase).values()) == 1
                for station in original_plan.stations for phase in (0, 1, 2)
            ),
            "v2_original_ab": pair(original_plan),
            "v2_swapped_ab": pair(swapped_plan),
            "v2_label_patch_ab": pair(label_plan),
            "v2_erased_handoff": erased,
        }


def main():
    print(json.dumps([
        compare_v1(RESET_ON_RETURN, Fraction(1)),
        compare_v1(PAIRED_EXIT, Fraction(1, 2)),
    ], ensure_ascii=False))
    print(json.dumps([
        compare_v2(RESET_ON_RETURN),
        compare_v2(PAIRED_EXIT),
    ], ensure_ascii=False))


if __name__ == "__main__":
    main()
