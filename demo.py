"""Run a bench-to-handover shift in two disposable SQLite files."""

import json
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.request import publish_report
from analysis.review_request import publish_review_report
from plans.freeze import freeze_plan
from plans.freeze_review import freeze_review_plan
from plans.snapshot import PlanOutcome
from reports.handover import handover
from reports.history import read_report
from reports.storage import open_archive
from source.corrections import amend
from source.intake import receive
from source.revisions import Station, TransferCount
from source.storage import open_source
from walks.replay import replay_walk


def _description(report):
    return {
        'report': report.report_id,
        'plan': report.plan_id,
        'release': str(report.release_probability),
        'retained_given_release': (None if report.retention_given_release is None
                                  else str(report.retention_given_release)),
    }


def _review_description(report):
    return {
        'report': report.report_id,
        'plan': report.plan_id,
        'revision': report.revision_id,
        'handoff_release': str(report.handoff_release_probability),
        'review_completion': (
            None if report.review_completion_given_handoff_release is None
            else str(report.review_completion_given_handoff_release)
        ),
    }


def _review_case(source, archive, case):
    revision = receive(
        source, case['batch'], [Station(*row) for row in case['stations']],
        case['release'], case['reject'],
        [TransferCount(*row) for row in case['counts']], labels=case['labels'],
    )
    plan = freeze_review_plan(source, archive, revision)
    report = publish_review_report(archive, plan.plan_id, 'A', ('A', 'B'))
    return revision, plan, report


def main():
    sample_path = Path(__file__).resolve().parent / 'samples' / 'shift.json'
    data = json.loads(sample_path.read_text(encoding='utf-8'))['returning']
    with TemporaryDirectory() as directory:
        source_path = Path(directory) / 'source.sqlite3'
        archive_path = Path(directory) / 'archive.sqlite3'
        with closing(open_archive(archive_path)) as archive:
            with closing(open_source(source_path)) as source:
                revision = receive(
                    source, data['batch'], [Station(*row) for row in data['stations']],
                    data['release'], data['reject'], [TransferCount(*row) for row in data['counts']],
                )
                plan = freeze_plan(source, archive, revision)
            walk = replay_walk(archive, plan.plan_id, 'A', (*data['walk'], PlanOutcome.RELEASE))
            original = publish_report(archive, plan.plan_id, 'A', ('A', 'B'))
            with closing(open_source(source_path)) as source:
                corrected = amend(source, revision, [TransferCount(*row) for row in data['amendment']])
                new_plan = freeze_plan(source, archive, corrected)
            amended = publish_report(archive, new_plan.plan_id, 'A', ('A', 'B'))
        with closing(open_archive(archive_path)) as archive:
            original_copy = read_report(archive, original.report_id)
            amended_copy = read_report(archive, amended.report_id)
            lists = {
                str(plan_id): [entry.report_id for entry in handover(archive, plan_id)]
                for plan_id in (plan.plan_id, new_plan.plan_id)
            }
        row = plan.row_for('A')
        assert (row['B'], row['C'], row[PlanOutcome.NEVER]) == (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
        assert walk.actual == ('A', 'B', 'A', 'C') and walk.retained == ('A', 'C')
        assert (original.release_probability, original.retention_given_release) == (Fraction(3, 7), Fraction(1, 3))
        assert (amended.release_probability, amended.retention_given_release) == (Fraction(1, 2), Fraction(0))
        assert original_copy == original and amended_copy == amended
        assert lists == {str(plan.plan_id): [original.report_id], str(new_plan.plan_id): [amended.report_id]}

        # V2 two-stage review: freeze while the source is open, then sign the
        # review report offline after the source library is closed.
        from review_examples import RESET_ON_RETURN

        with closing(open_archive(archive_path)) as archive:
            with closing(open_source(source_path)) as source:
                review_revision, review_plan, offline_report = _review_case(
                    source, archive, RESET_ON_RETURN
                )
                swapped_revision = amend(
                    source, review_revision,
                    [TransferCount(*row) for row in RESET_ON_RETURN['replacements']],
                )
                swapped_plan = freeze_review_plan(source, archive, swapped_revision)
                label_revision = amend(
                    source, review_revision, [],
                    labels=RESET_ON_RETURN['label_only_patch'],
                )
                label_plan = freeze_review_plan(source, archive, label_revision)
            # The source is closed here; publication uses the frozen archive only.
            swapped_report = publish_review_report(
                archive, swapped_plan.plan_id, 'A', ('A', 'B')
            )
            erased_report = publish_review_report(
                archive, review_plan.plan_id, 'B', ('B', 'C')
            )
            label_report = publish_review_report(
                archive, label_plan.plan_id, 'A', ('A', 'B')
            )
            assert (offline_report.handoff_release_probability,
                    offline_report.review_completion_given_handoff_release) == (Fraction(1), Fraction(1, 2))
            assert (swapped_report.handoff_release_probability,
                    swapped_report.review_completion_given_handoff_release) == (Fraction(1), Fraction(0))
            assert (erased_report.handoff_release_probability,
                    erased_report.review_completion_given_handoff_release) == (0, None)
            assert (label_report.handoff_release_probability,
                    label_report.review_completion_given_handoff_release) == (Fraction(1), Fraction(1))
            picked = read_report(archive, offline_report.report_id)
            assert picked == offline_report
            review_handover = [
                entry.report_id for entry in handover(archive, review_plan.plan_id)
            ]
            assert review_handover == [offline_report.report_id, erased_report.report_id]

        with closing(open_archive(archive_path)) as reopened:
            reopened_pickup = read_report(reopened, offline_report.report_id)
            assert reopened_pickup == offline_report
            picked = reopened_pickup

        print(json.dumps({
            'batch': data['batch'],
            'source_revisions': [plan.revision_id, new_plan.revision_id],
            'next_outcomes_from_A': {
                key.value if isinstance(key, PlanOutcome) else key: str(value) for key, value in row.items()
            },
            'walk': {'actual': walk.actual, 'retained': walk.retained, 'erasures': walk.erasures,
                     'terminal': walk.terminal.value},
            'original_report': _description(original_copy),
            'amended_report': _description(amended_copy),
            'handover': lists,
            'review_reports': {
                'offline_reset_on_return': _review_description(offline_report),
                'swapped_order': _review_description(swapped_report),
                'erased_handoff': _review_description(erased_report),
                'label_only_correction': _review_description(label_report),
                'reopened_pickup': _review_description(picked),
            },
        }, ensure_ascii=False))


if __name__ == '__main__':
    main()
