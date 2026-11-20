from fractions import Fraction

from analysis.request import InvalidReviewRequest as V1Invalid
from analysis.request import publish_report
from analysis.review_request import InvalidReviewRequest, publish_review_report
from plans.catalog import PlanNotFound, load_plan
from plans.freeze import freeze_plan
from plans.freeze_review import freeze_review_plan
from plans.snapshot import PlanOutcome
from reports.handover import HandoverEntry, handover
from reports.history import ReportNotFound, read_report
from reports.review_publish import PublishError
from reports.review_receipt import FormalReviewReport, ReviewReceipt
from review_examples import PAIRED_EXIT, RESET_ON_RETURN
from source.corrections import amend
from source.intake import receive
from source.revisions import Station, TransferCount
from tests.fixtures import DatabaseCase
from walks.replay import replay_walk
from walks.session import InvalidWalk


def _build(source, case):
    return receive(
        source, case['batch'], [Station(*row) for row in case['stations']],
        case['release'], case['reject'],
        [TransferCount(*row) for row in case['counts']], labels=case['labels'],
    )


class TestReviewReports(DatabaseCase):
    def _reset_plan(self):
        revision = _build(self.source, RESET_ON_RETURN)
        return freeze_review_plan(self.source, self.archive, revision), revision

    def test_reset_on_return_example(self):
        plan, _ = self._reset_plan()
        report = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        self.assertEqual(
            (report.handoff_release_probability,
             report.review_completion_given_handoff_release),
            (Fraction(1), Fraction(1, 2)),
        )
        self.assertEqual(report.plan_id, plan.plan_id)
        self.assertEqual(report.revision_id, plan.revision_id)
        self.assertEqual(report.handoff, ('A', 'B'))
        self.assertEqual(report.start, 'A')
        self.assertEqual(report.receipt, ReviewReceipt(report.report_id, plan.plan_id))

    def test_empty_subgroup_is_none_and_nonempty_zero_is_a_fraction(self):
        plan, _ = self._reset_plan()
        erased = publish_review_report(self.archive, plan.plan_id, 'B', ('B', 'C'))
        self.assertEqual(erased.handoff_release_probability, Fraction(0))
        self.assertIsNone(erased.review_completion_given_handoff_release)
        swapped = amend(
            self.source, plan.revision_id,
            [TransferCount(*row) for row in RESET_ON_RETURN['replacements']],
        )
        swapped_plan = freeze_review_plan(self.source, self.archive, swapped)
        zero_ratio = publish_review_report(
            self.archive, swapped_plan.plan_id, 'A', ('A', 'B')
        )
        self.assertEqual(zero_ratio.handoff_release_probability, Fraction(1))
        self.assertEqual(zero_ratio.review_completion_given_handoff_release, Fraction(0))
        self.assertIs(type(zero_ratio.review_completion_given_handoff_release), Fraction)

    def test_label_only_patch_and_paired_exit_examples(self):
        plan, revision = self._reset_plan()
        cleared_revision = amend(
            self.source, revision, [], labels=RESET_ON_RETURN['label_only_patch']
        )
        cleared_plan = freeze_review_plan(self.source, self.archive, cleared_revision)
        cleared = publish_review_report(self.archive, cleared_plan.plan_id, 'A', ('A', 'B'))
        self.assertEqual(
            (cleared.handoff_release_probability,
             cleared.review_completion_given_handoff_release),
            (Fraction(1), Fraction(1)),
        )
        original = _build(self.source, PAIRED_EXIT)
        paired_plan = freeze_review_plan(self.source, self.archive, original)
        first = publish_review_report(self.archive, paired_plan.plan_id, 'A', ('A', 'B'))
        # The fork reaching B has already passed recheck P; witness Q then
        # completes the review before the release.
        self.assertEqual(
            (first.handoff_release_probability,
             first.review_completion_given_handoff_release),
            (Fraction(1, 2), Fraction(1)),
        )
        changed = amend(
            self.source, original,
            [TransferCount(*row) for row in PAIRED_EXIT['replacements']],
        )
        changed_plan = freeze_review_plan(self.source, self.archive, changed)
        second = publish_review_report(self.archive, changed_plan.plan_id, 'A', ('A', 'B'))
        # After the correction the B branch enters via X, which has no recheck
        # label, so witness Q cannot complete the review.
        self.assertEqual(
            (second.handoff_release_probability,
             second.review_completion_given_handoff_release),
            (Fraction(1, 2), Fraction(0)),
        )

    def test_report_round_trip_and_immutable_history(self):
        plan, revision = self._reset_plan()
        report = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        self.reopen_archive()
        restored = read_report(self.archive, report.report_id)
        self.assertIsInstance(restored, FormalReviewReport)
        self.assertEqual(restored, report)
        # Re-issuing after a correction never mutates the original report.
        with self.assertRaises(PlanNotFound):
            load_plan(self.archive, plan.plan_id + 50)
        self.assertEqual(restored.handoff, ('A', 'B'))

    def test_handover_lists_signing_order_for_one_plan(self):
        plan, _ = self._reset_plan()
        first = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        second = publish_review_report(self.archive, plan.plan_id, 'B', ('B', 'C'))
        self.assertEqual(
            handover(self.archive, plan.plan_id),
            [HandoverEntry(first.report_id, 'A'), HandoverEntry(second.report_id, 'B')],
        )
        self.reopen_archive()
        self.assertEqual(
            handover(self.archive, plan.plan_id),
            [HandoverEntry(first.report_id, 'A'), HandoverEntry(second.report_id, 'B')],
        )

    def test_unknown_plan_and_invalid_requests(self):
        plan, _ = self._reset_plan()
        with self.assertRaises(PlanNotFound):
            publish_review_report(self.archive, plan.plan_id + 40, 'A', ('A', 'B'))
        for start, pair in (
            ('Z', ('A', 'B')),
            ('A', ('Z', 'B')),
            ('A', ('A', 'Z')),
            ('A', ('A',)),
            ('A', 'AB'),
        ):
            with self.subTest(start=start, pair=pair):
                with self.assertRaises(InvalidReviewRequest):
                    publish_review_report(self.archive, plan.plan_id, start, pair)
        self.assertEqual(handover(self.archive, plan.plan_id), [])

    def test_list_handoff_input_is_normalized_to_a_tuple(self):
        plan, _ = self._reset_plan()
        report = publish_review_report(self.archive, plan.plan_id, 'A', ['A', 'B'])
        self.assertEqual(report.handoff, ('A', 'B'))
        self.assertEqual(read_report(self.archive, report.report_id).handoff, ('A', 'B'))

    def test_v1_plan_is_rejected_by_review_publication(self):
        revision = _build(self.source, RESET_ON_RETURN)
        v1_plan = freeze_plan(self.source, self.archive, revision)
        with self.assertRaises(InvalidReviewRequest):
            publish_review_report(self.archive, v1_plan.plan_id, 'A', ('A', 'B'))

    def test_v2_plan_is_rejected_by_v1_publication_and_walks(self):
        plan, _ = self._reset_plan()
        with self.assertRaises(V1Invalid):
            publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        with self.assertRaises(InvalidWalk):
            replay_walk(self.archive, plan.plan_id, 'A', (PlanOutcome.RELEASE,))

    def test_failed_commit_leaves_no_report_or_handover_entry(self):
        plan, _ = self._reset_plan()
        existing = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'B'))

        def fail(_receipt):
            raise RuntimeError('shift ended before confirmation')

        with self.assertRaises(PublishError) as raised:
            publish_review_report(
                self.archive, plan.plan_id, 'B', ('B', 'C'), before_commit=fail
            )
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertEqual(
            handover(self.archive, plan.plan_id),
            [HandoverEntry(existing.report_id, 'A')],
        )
        self.reopen_archive()
        with self.assertRaises(ReportNotFound):
            read_report(self.archive, existing.report_id + 1)
        self.assertEqual(read_report(self.archive, existing.report_id), existing)

    def test_failed_commit_is_retryable(self):
        plan, _ = self._reset_plan()

        def fail(_receipt):
            raise RuntimeError('boom')

        with self.assertRaises(PublishError):
            publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'B'), before_commit=fail)
        report = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        self.assertEqual(handover(self.archive, plan.plan_id),
                         [HandoverEntry(report.report_id, 'A')])

    def test_before_commit_receives_the_pending_receipt(self):
        plan, _ = self._reset_plan()
        seen = []
        report = publish_review_report(
            self.archive, plan.plan_id, 'A', ('A', 'B'),
            before_commit=lambda receipt: seen.append(receipt),
        )
        self.assertEqual(seen, [ReviewReceipt(report.report_id, plan.plan_id)])

    def test_old_report_survives_correction_and_reopen(self):
        plan, revision = self._reset_plan()
        original = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        corrected_revision = amend(
            self.source, revision,
            [TransferCount(*row) for row in RESET_ON_RETURN['replacements']],
        )
        corrected_plan = freeze_review_plan(self.source, self.archive, corrected_revision)
        corrected = publish_review_report(
            self.archive, corrected_plan.plan_id, 'A', ('A', 'B')
        )
        self.reopen_archive()
        self.assertEqual(read_report(self.archive, original.report_id), original)
        self.assertEqual(read_report(self.archive, corrected.report_id), corrected)
        self.assertEqual(
            handover(self.archive, plan.plan_id),
            [HandoverEntry(original.report_id, 'A')],
        )
        self.assertEqual(
            handover(self.archive, corrected_plan.plan_id),
            [HandoverEntry(corrected.report_id, 'A')],
        )

    def test_unknown_report_and_plan_lookups(self):
        with self.assertRaises(ReportNotFound):
            read_report(self.archive, 5)
        with self.assertRaises(PlanNotFound):
            handover(self.archive, 7)
