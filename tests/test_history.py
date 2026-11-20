from fractions import Fraction

from analysis.request import publish_report
from plans.catalog import load_plan
from plans.freeze import freeze_plan
from reports.handover import HandoverEntry, handover
from reports.history import read_report
from reports.receipt import Receipt
from reports.storage import initialize_archive
from source.corrections import amend
from source.intake import BatchConflict
from source.revisions import RevisionNotFound, TransferCount, load_revision
from source.storage import initialize_source
from source.validation import InvalidCounts
from tests.fixtures import DatabaseCase, receive_sample, sample


class TestHistory(DatabaseCase):
    def _issue_and_correct(self):
        data = sample('straight')
        original_revision = receive_sample(self.source, data)
        old_plan = freeze_plan(self.source, self.archive, original_revision)
        old_report = publish_report(self.archive, old_plan.plan_id, 'A', ('A', 'B'))
        corrected = amend(self.source, original_revision, [TransferCount(*row) for row in data['amendment']])
        new_plan = freeze_plan(self.source, self.archive, corrected)
        self.source.close()
        new_report = publish_report(self.archive, new_plan.plan_id, 'A', ('A', 'B'))
        return old_plan, old_report, new_plan, new_report

    def test_old_report_after_correction(self):
        old_plan, old_report, new_plan, new_report = self._issue_and_correct()
        self.reopen_archive()
        old = read_report(self.archive, old_report.report_id)
        new = read_report(self.archive, new_report.report_id)
        self.assertNotEqual(old_plan.plan_id, new_plan.plan_id)
        self.assertEqual((old.plan_id, new.plan_id), (old_plan.plan_id, new_plan.plan_id))
        self.assertEqual((old.release_probability, new.release_probability), (Fraction(1), Fraction(1)))
        self.assertEqual((old.retention_given_release, new.retention_given_release), (Fraction(1, 2), Fraction(0)))
        self.assertEqual(handover(self.archive, old.plan_id), [HandoverEntry(old.report_id, 'A')])
        self.assertEqual(handover(self.archive, new.plan_id), [HandoverEntry(new.report_id, 'A')])

    def test_count_replacement(self):
        data = sample('straight')
        data['counts'].append(['A', 'B', 2])
        parent = receive_sample(self.source, data)
        original = load_revision(self.source, parent)
        branch = amend(self.source, parent, [TransferCount('A', 'C', 3)])
        child = amend(self.source, parent, [TransferCount('A', 'B', 0)])
        self.assertNotEqual(child, branch)
        self.assertEqual(load_revision(self.source, parent), original)
        corrected = load_revision(self.source, child)
        self.assertEqual(corrected.parent_id, parent)
        self.assertEqual([row.count for row in corrected.counts if row.key == ('A', 'B')], [0])
        self.assertIn(TransferCount('A', 'C', 1), corrected.counts)
        old_plan = freeze_plan(self.source, self.archive, parent)
        new_plan = freeze_plan(self.source, self.archive, child)
        self.assertEqual(old_plan.row_for('A')['B'], Fraction(3, 4))
        self.assertEqual(new_plan.row_for('A')['B'], Fraction(0))
        self.assertEqual(new_plan.row_for('A')['C'], Fraction(1))

    def test_invalid_amend(self):
        revision = receive_sample(self.source, sample('straight'))
        original = load_revision(self.source, revision)
        with self.assertRaises(RevisionNotFound):
            amend(self.source, revision + 1, [TransferCount('A', 'B', 0)])
        for changes in ([TransferCount('A', 'B', -1)], [TransferCount('A', 'B', True)],
                        [TransferCount('A', 'missing', 0)],
                        [TransferCount('A', 'B', 0), TransferCount('A', 'B', 2)]):
            with self.subTest(changes=changes):
                with self.assertRaises(InvalidCounts):
                    amend(self.source, revision, changes)
        self.assertEqual(self.revision_ids(), [revision])
        self.assertEqual(load_revision(self.source, revision), original)

    def test_receipt_identity(self):
        old_plan, old_report, new_plan, new_report = self._issue_and_correct()
        self.reopen_archive()
        for plan, published, expected in ((old_plan, old_report, Fraction(1, 2)),
                                          (new_plan, new_report, Fraction(0))):
            received = read_report(self.archive, published.report_id)
            self.assertEqual(received, published)
            self.assertEqual(received.retention_given_release, expected)
            self.assertEqual(received.receipt, Receipt(published.report_id, plan.plan_id))

    def test_reopen_initialization(self):
        old_plan, old_report, new_plan, new_report = self._issue_and_correct()
        self.reopen_source()
        self.reopen_archive()
        initialize_source(self.source)
        initialize_archive(self.archive)
        original = load_revision(self.source, old_plan.revision_id)
        corrected = load_revision(self.source, new_plan.revision_id)
        self.assertEqual(corrected.parent_id, original.revision_id)
        self.assertIn(TransferCount('A', 'B', 1), original.counts)
        self.assertIn(TransferCount('A', 'B', 0), corrected.counts)
        for plan, report in ((old_plan, old_report), (new_plan, new_report)):
            self.assertEqual(load_plan(self.archive, plan.plan_id), plan)
            self.assertEqual(read_report(self.archive, report.report_id), report)
            self.assertEqual(handover(self.archive, plan.plan_id), [HandoverEntry(report.report_id, 'A')])
        with self.assertRaises(BatchConflict):
            receive_sample(self.source, sample('straight'))
        self.assertEqual(self.revision_ids(), [original.revision_id, corrected.revision_id])
