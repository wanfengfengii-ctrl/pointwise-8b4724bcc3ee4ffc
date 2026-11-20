from fractions import Fraction

from analysis.review_request import publish_review_report
from plans.freeze_review import freeze_review_plan
from plans.review_transfer import apply_label
from plans.snapshot import PlanOutcome
from source.corrections import amend
from source.intake import receive
from source.revisions import Station, TransferCount
from source.validation import InvalidCounts
from tests.fixtures import DatabaseCase


class TestPhaseMechanics(DatabaseCase):
    def test_label_transition_table(self):
        self.assertEqual(apply_label(0, 'recheck'), 1)
        self.assertEqual(apply_label(1, 'recheck'), 1)
        self.assertEqual(apply_label(2, 'recheck'), 2)
        self.assertEqual(apply_label(0, 'witness'), 0)
        self.assertEqual(apply_label(1, 'witness'), 2)
        self.assertEqual(apply_label(2, 'witness'), 2)
        for phase in (0, 1, 2):
            self.assertEqual(apply_label(phase, 'reset'), 0)
            self.assertEqual(apply_label(phase, None), phase)

    def test_start_station_label_never_fires_at_start(self):
        revision = receive(
            self.source, 'start-label',
            (Station('A', True), Station('G', False)), 'pass', 'fail',
            (TransferCount('A', 'G', 1), TransferCount('G', 'pass', 1),
             TransferCount('A', 'pass', 1)),
            labels={'A': 'recheck'},
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        row = plan.row_for('A', 0)
        self.assertEqual(row[(PlanOutcome.RELEASE, 0)], Fraction(1))
        report = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'A'))
        self.assertEqual(
            (report.handoff_release_probability,
             report.review_completion_given_handoff_release),
            (0, None),
        )

    def test_private_reset_on_return_to_start(self):
        revision = receive(
            self.source, 'return-start',
            (Station('A', True), Station('R', False), Station('P', False)),
            'pass', 'fail',
            (TransferCount('A', 'P', 1), TransferCount('P', 'R', 1),
             TransferCount('R', 'A', 1), TransferCount('A', 'pass', 1)),
            labels={'P': 'recheck', 'R': 'reset'},
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        for entry_phase in (0, 2):
            row = plan.row_for('A', entry_phase)
            self.assertEqual(row[('A', 0)], Fraction(1, 2))
            self.assertEqual(row[(PlanOutcome.RELEASE, entry_phase)], Fraction(1, 2))

    def test_public_self_return_applies_arrival_label_once(self):
        revision = receive(
            self.source, 'self-return', (Station('A', True),), 'pass', 'fail',
            (TransferCount('A', 'A', 1), TransferCount('A', 'pass', 1)),
            labels={'A': 'recheck'},
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        row = plan.row_for('A', 0)
        self.assertEqual(row[('A', 1)], Fraction(1, 2))
        self.assertEqual(row[(PlanOutcome.RELEASE, 0)], Fraction(1, 2))
        # From phase 1 the self-return stays at phase 1 (recheck is monotone).
        advanced = plan.row_for('A', 1)
        self.assertEqual(advanced[('A', 1)], Fraction(1, 2))

    def test_witness_requires_a_prior_recheck(self):
        revision = receive(
            self.source, 'witness-only',
            (Station('A', True), Station('Q', False)), 'pass', 'fail',
            (TransferCount('A', 'Q', 1), TransferCount('Q', 'pass', 1)),
            labels={'Q': 'witness'},
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        row = plan.row_for('A', 0)
        self.assertEqual(row[(PlanOutcome.RELEASE, 0)], Fraction(1))
        report = publish_review_report(self.archive, plan.plan_id, 'A', ('A', 'A'))
        self.assertEqual(report.handoff_release_probability, 0)

    def test_reject_and_never_carry_the_arrival_phase(self):
        revision = receive(
            self.source, 'phased-exits',
            (Station('A', True), Station('B', True), Station('G', False),
             Station('H', False)),
            'pass', 'fail',
            (TransferCount('A', 'B', 1), TransferCount('A', 'G', 1),
             TransferCount('A', 'H', 1), TransferCount('G', 'fail', 1),
             TransferCount('H', 'H', 1), TransferCount('B', 'pass', 1)),
            labels={'B': 'recheck'},
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        row = plan.row_for('A', 2)
        self.assertEqual(row[('B', 2)], Fraction(1, 3))
        self.assertEqual(row[(PlanOutcome.REJECT, 2)], Fraction(1, 3))
        self.assertEqual(row[(PlanOutcome.NEVER, None)], Fraction(1, 3))

    def test_label_mapping_validation(self):
        stations = (Station('A', True), Station('G', False))
        for labels in (
            'recheck', ['recheck'], 42, {'G': 'rework'}, {'G': 0},
            {'G': True}, {'unknown': 'reset'}, {None: 'recheck'},
        ):
            with self.subTest(labels=labels):
                with self.assertRaises(InvalidCounts):
                    receive(
                        self.source, 'bad', stations, 'pass', 'fail',
                        (TransferCount('A', 'pass', 1),), labels=labels,
                    )
        self.assertEqual(self.revision_ids(), [])

    def test_amend_clear_requires_none_value(self):
        parent = receive(
            self.source, 'clear', (Station('A', True), Station('G', False)),
            'pass', 'fail', (TransferCount('A', 'pass', 1),),
            labels={'G': 'recheck'},
        )
        child = amend(self.source, parent, [], labels={'G': None})
        from source.revisions import load_revision
        self.assertEqual(load_revision(self.source, child).labels, {})
        self.assertEqual(
            load_revision(self.source, parent).labels, {'G': 'recheck'}
        )
