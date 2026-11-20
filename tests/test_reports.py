import json
from fractions import Fraction

from analysis.request import InvalidReviewRequest, publish_report
from plans.catalog import PlanNotFound
from plans.freeze import freeze_plan
from reports.handover import HandoverEntry, handover
from reports.history import ReportNotFound, read_report
from reports.publish import PublishError
from reports.receipt import Receipt
from source.intake import receive
from source.revisions import Station, TransferCount
from tests.fixtures import DatabaseCase, sample


class TestReports(DatabaseCase):
    def test_offline_branch(self):
        plan = self.freeze('straight')
        self.source.close()
        report = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        self.assertEqual(report.release_probability, Fraction(1))
        self.assertEqual(report.retention_given_release, Fraction(1, 2))
        self.assertEqual(report.receipt, Receipt(report.report_id, plan.plan_id))
        self.assertEqual(handover(self.archive, plan.plan_id), [HandoverEntry(report.report_id, 'A')])

    def test_returning_branch(self):
        plan = self.freeze('returning')
        self.source.close()
        self.reopen_archive()
        report = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        expected = {'release': '3/7', 'conditional': '1/3'}
        actual = {'release': str(report.release_probability),
                  'conditional': str(report.retention_given_release)}
        self.assertEqual(actual, expected, 'ROUTE_RELEASE_MISMATCH')
        self.assertEqual(report.plan_id, plan.plan_id)
        self.assertEqual(report.handoff, ('A', 'B'))
        self.assertEqual(read_report(self.archive, report.report_id), report)
        entries = handover(self.archive, plan.plan_id)
        self.assertEqual(entries, [HandoverEntry(report.report_id, 'A')])
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v5.returning_branch',
            'input': {'plan_id': plan.plan_id, 'start': 'A', 'handoff': ['A', 'B'],
                      'counts': sample('returning')['counts']},
            'expected': expected,
            'actual': actual,
            'downstream_expected': [{'report_id': report.report_id, 'start': 'A'}],
            'downstream_actual': [{'report_id': entry.report_id, 'start': entry.start} for entry in entries],
            'code_paths': ['plans/transfer.py', 'analysis/release.py', 'analysis/route_event.py',
                           'reports/publish.py', 'reports/handover.py'],
            'oracle': 'At A the retry mass is 1/8. Direct success via B is 1/8 and via C is 1/4. '
                      'Sum the geometric series for each release branch. Only the final B branch retains A to B.',
        }, sort_keys=True), flush=True)

    def test_erased_edge(self):
        plan = self.freeze('erased')
        self.source.close()
        report = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        self.assertEqual(report.release_probability, Fraction(1))
        self.assertEqual(report.retention_given_release, Fraction(0))
        self.assertEqual(read_report(self.archive, report.report_id), report)

    def test_distinct_prefixes_at_same_public_station(self):
        # D is reached via B or C with equal probability. After reaching D,
        # excursions D -> B -> D leave either prefix intact. Every run releases.
        revision = receive(
            self.source, 'fork', [Station(name, True) for name in 'ABCD'], 'pass', 'fail',
            [TransferCount(*row) for row in (
                ('A', 'B', 1), ('A', 'C', 1), ('B', 'D', 1), ('C', 'D', 1),
                ('D', 'B', 1), ('D', 'pass', 1),
            )],
        )
        plan = freeze_plan(self.source, self.archive, revision)
        self.source.close()
        report = publish_report(self.archive, plan.plan_id, 'A', ('B', 'D'))
        self.assertEqual(report.release_probability, Fraction(1))
        self.assertEqual(report.retention_given_release, Fraction(1, 2))

    def test_zero_condition(self):
        plan = self.freeze('zero')
        self.source.close()
        published = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        self.reopen_archive()
        restored = read_report(self.archive, published.report_id)
        self.assertEqual(restored.release_probability, Fraction(1))
        self.assertEqual(restored.retention_given_release, Fraction(0))
        self.assertIs(type(restored.retention_given_release), Fraction)

    def test_no_release(self):
        plan = self.freeze('closed')
        self.source.close()
        report = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        self.assertEqual(report.release_probability, Fraction(0))
        self.assertIsNone(report.retention_given_release)
        self.reopen_archive()
        recovered = read_report(self.archive, report.report_id)
        self.assertEqual(recovered, report)
        self.assertIsNone(recovered.retention_given_release)
        self.assertEqual(handover(self.archive, plan.plan_id), [HandoverEntry(report.report_id, 'A')])

    def test_invalid_request(self):
        plan = self.freeze('straight')
        with self.assertRaises(PlanNotFound):
            publish_report(self.archive, plan.plan_id + 1, 'A', ('A', 'B'))
        for start, handoff in (('outside', ('A', 'B')), ('A', ('outside', 'B')),
                               ('A', ('A', 'outside')), ('A', ('A',))):
            with self.subTest(start=start, handoff=handoff):
                with self.assertRaises(InvalidReviewRequest):
                    publish_report(self.archive, plan.plan_id, start, handoff)
        self.assertEqual(handover(self.archive, plan.plan_id), [])
        with self.assertRaises(ReportNotFound):
            read_report(self.archive, 1)

    def test_issue_order(self):
        plan = self.freeze('straight')
        other = self.freeze('zero')
        first = publish_report(self.archive, plan.plan_id, 'B', ('A', 'B'))
        publish_report(self.archive, other.plan_id, 'A', ('A', 'C'))
        second = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        expected = [HandoverEntry(first.report_id, 'B'), HandoverEntry(second.report_id, 'A')]
        self.assertEqual(handover(self.archive, plan.plan_id), expected)
        self.reopen_archive()
        self.assertEqual(handover(self.archive, plan.plan_id), expected)

    def test_empty_and_missing(self):
        plan = self.freeze('straight')
        self.assertEqual(handover(self.archive, plan.plan_id), [])
        with self.assertRaises(PlanNotFound):
            handover(self.archive, plan.plan_id + 1)
        with self.assertRaises(ReportNotFound):
            read_report(self.archive, 100)

    def test_failed_commit(self):
        plan = self.freeze('straight')
        original = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))

        def fail(_receipt):
            raise RuntimeError('shift ended before confirmation')

        with self.assertRaises(PublishError) as raised:
            publish_report(self.archive, plan.plan_id, 'B', ('A', 'B'), before_commit=fail)
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertEqual(handover(self.archive, plan.plan_id), [HandoverEntry(original.report_id, 'A')])
        self.assertEqual(read_report(self.archive, original.report_id), original)

    def test_no_orphan(self):
        plan = self.freeze('straight')
        original = publish_report(self.archive, plan.plan_id, 'A', ('A', 'B'))
        staged = []

        def fail(receipt):
            staged.append(receipt)
            raise RuntimeError('report confirmation interrupted')

        with self.assertRaises(PublishError):
            publish_report(self.archive, plan.plan_id, 'B', ('A', 'B'), before_commit=fail)
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0].plan_id, plan.plan_id)
        self.assertNotEqual(staged[0].report_id, original.report_id)
        self.reopen_archive()
        with self.assertRaises(ReportNotFound):
            read_report(self.archive, staged[0].report_id)
        self.assertEqual(read_report(self.archive, original.report_id), original)
        self.assertEqual(handover(self.archive, plan.plan_id), [HandoverEntry(original.report_id, 'A')])
