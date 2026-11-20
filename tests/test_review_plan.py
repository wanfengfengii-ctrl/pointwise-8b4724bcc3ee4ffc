from fractions import Fraction

from plans.catalog import PlanNotFound, load_plan
from plans.freeze import FreezeError as V1FreezeError, freeze_plan
from plans.freeze_review import freeze_review_plan
from plans.review_snapshot import PHASES, ReviewPlan, review_outcome_keys
from plans.snapshot import PlanOutcome
from source.corrections import amend
from source.intake import receive
from source.revisions import Station, TransferCount
from source.validation import InvalidCounts
from tests.fixtures import DatabaseCase


def _labeled(source, batch='review-plan', labels=None, counts=None, stations=None):
    stations = stations or (
        Station('A', True), Station('B', True), Station('C', True),
        Station('P', False), Station('Q', False), Station('R', False),
    )
    counts = counts or (
        TransferCount('A', 'P', 1), TransferCount('P', 'Q', 1),
        TransferCount('Q', 'B', 1), TransferCount('B', 'pass', 1),
        TransferCount('B', 'C', 1), TransferCount('C', 'R', 1),
        TransferCount('R', 'B', 1),
    )
    return receive(source, batch, stations, 'pass', 'fail', counts, labels=labels)


class TestReviewFreeze(DatabaseCase):
    def _plan(self, labels=None):
        revision = _labeled(self.source, labels=labels or {
            'P': 'recheck', 'Q': 'witness', 'R': 'reset',
        })
        return freeze_review_plan(self.source, self.archive, revision)

    def test_plan_identity_and_canonical_keys(self):
        plan = self._plan()
        self.assertIsInstance(plan, ReviewPlan)
        self.assertEqual(plan.plan_version, 2)
        self.assertEqual(plan.stations, ('A', 'B', 'C'))
        keys = review_outcome_keys(plan.stations)
        self.assertEqual(keys[-1], (PlanOutcome.NEVER, None))
        self.assertIn((PlanOutcome.RELEASE, 2), keys)
        for station in plan.stations:
            for phase in PHASES:
                row = plan.row_for(station, phase)
                self.assertEqual(tuple(row), keys)
                self.assertTrue(all(type(value) is Fraction and value >= 0 for value in row.values()))
                self.assertEqual(sum(row.values()), 1)

    def test_every_entry_phase_is_available_even_when_unreachable(self):
        plan = self._plan()
        for phase in PHASES:
            self.assertEqual(sum(plan.row_for('A', phase).values()), 1)

    def test_arrival_label_is_applied_once_in_frozen_rows(self):
        plan = self._plan()
        row = plan.row_for('A', 0)
        # A -> P (recheck 0->1) -> Q (witness 1->2) -> B arrives complete.
        self.assertEqual(row[('B', 2)], Fraction(1))
        self.assertEqual(row[('B', 0)], Fraction(0))
        # B half releases immediately, half routes directly to C. Labels only
        # fire on arrivals, so the direct B -> C segment preserves the phase;
        # R resets only on the later C -> R -> B return.
        b_row = plan.row_for('B', 2)
        self.assertEqual(b_row[(PlanOutcome.RELEASE, 2)], Fraction(1, 2))
        self.assertEqual(b_row[('C', 2)], Fraction(1, 2))
        c_row = plan.row_for('C', 0)
        self.assertEqual(c_row[('B', 0)], Fraction(1))

    def test_reset_on_private_return_and_self_returns(self):
        revision = receive(
            self.source, 'self',
            (Station('A', True), Station('G', False)),
            'pass', 'fail',
            (TransferCount('A', 'G', 1), TransferCount('G', 'A', 1),
             TransferCount('A', 'pass', 1)),
            labels={'G': 'reset'},
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        row = plan.row_for('A', 2)
        self.assertEqual(row[('A', 0)], Fraction(1, 2))
        self.assertEqual(row[(PlanOutcome.RELEASE, 2)], Fraction(1, 2))

    def test_never_column_covers_private_traps_and_missing_edges(self):
        revision = receive(
            self.source, 'trap',
            (Station('A', True), Station('H', False)),
            'pass', 'fail',
            (TransferCount('A', 'H', 1), TransferCount('H', 'H', 1)),
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        for phase in PHASES:
            self.assertEqual(
                plan.row_for('A', phase)[(PlanOutcome.NEVER, None)], Fraction(1)
            )

    def test_terminal_rows_keep_the_arrival_phase(self):
        revision = receive(
            self.source, 'term', (Station('A', True),), 'pass', 'fail',
            (TransferCount('A', 'pass', 1), TransferCount('A', 'fail', 1)),
        )
        plan = freeze_review_plan(self.source, self.archive, revision)
        row = plan.row_for('A', 2)
        self.assertEqual(row[(PlanOutcome.RELEASE, 2)], Fraction(1, 2))
        self.assertEqual(row[(PlanOutcome.REJECT, 2)], Fraction(1, 2))

    def test_private_names_counts_and_labels_leave_no_archive_trace(self):
        plan = self._plan()
        payload, = self.archive.execute(
            'SELECT payload FROM fixed_plans WHERE plan_id = ?', (plan.plan_id,)
        ).fetchone()
        for secret in ('P', 'Q', 'R', 'recheck', 'witness', 'reset'):
            self.assertNotIn(secret, payload)

    def test_plan_round_trip_after_reopen(self):
        plan = self._plan()
        self.reopen_archive()
        restored = load_plan(self.archive, plan.plan_id)
        self.assertEqual(restored, plan)
        self.assertIsInstance(restored, ReviewPlan)

    def test_unknown_plan_number_raises_plan_not_found(self):
        self._plan()
        with self.assertRaises(PlanNotFound):
            load_plan(self.archive, 99)

    def test_freeze_failure_leaves_no_new_plan(self):
        revision = _labeled(self.source)
        before = [row[0] for row in self.archive.execute('SELECT plan_id FROM fixed_plans')]
        with self.assertRaises(V1FreezeError):
            freeze_review_plan(self.source, self.archive, revision + 10)
        after = [row[0] for row in self.archive.execute('SELECT plan_id FROM fixed_plans')]
        self.assertEqual(before, after)
    def test_v1_and_v2_share_the_plan_number_space(self):
        revision = _labeled(self.source, labels={})
        v1 = freeze_plan(self.source, self.archive, revision)
        v2 = freeze_review_plan(self.source, self.archive, revision)
        self.assertEqual(v2.plan_id, v1.plan_id + 1)
        self.assertIs(load_plan(self.archive, v1.plan_id).__class__, type(v1))

    def test_amended_revision_freezes_independent_rows(self):
        parent = _labeled(self.source, labels={'P': 'recheck', 'R': 'reset'})
        child = amend(self.source, parent, [TransferCount('R', 'B', 0)], labels={'R': None})
        original = freeze_review_plan(self.source, self.archive, parent)
        corrected = freeze_review_plan(self.source, self.archive, child)
        self.assertNotEqual(original.rows, corrected.rows)
        self.assertEqual(corrected.revision_id, child)

    def test_invalid_label_in_revision_is_rejected_at_freeze(self):
        # Hand-craft an intake failure path: invalid labels never create rows.
        with self.assertRaises(InvalidCounts):
            receive(self.source, 'bad', (Station('A', True),), 'pass', 'fail',
                    (TransferCount('A', 'pass', 1),), labels={'A': 'nope'})

    def test_unknown_station_and_phase_key_errors(self):
        plan = self._plan()
        with self.assertRaises(KeyError):
            plan.row_for('Z', 0)
        with self.assertRaises(ValueError):
            plan.row_for('A', 3)
