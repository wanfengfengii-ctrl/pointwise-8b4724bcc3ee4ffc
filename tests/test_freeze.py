from fractions import Fraction

from plans.catalog import PlanNotFound, load_plan
from plans.freeze import FreezeError, freeze_plan
from plans.snapshot import PlanOutcome
from source.intake import BatchConflict, receive
from source.revisions import Station, TransferCount, load_revision
from source.validation import InvalidCounts
from tests.fixtures import DatabaseCase, receive_sample, sample


class TestFreeze(DatabaseCase):
    def test_public_return_and_trap(self):
        plan = self.freeze('self_trap')
        self.assertEqual(plan.row_for('A'), {
            'A': Fraction(1, 2), PlanOutcome.RELEASE: Fraction(0),
            PlanOutcome.REJECT: Fraction(0), PlanOutcome.NEVER: Fraction(1, 2),
        })

    def test_indirect_trap(self):
        plan = self.freeze('returning')
        row = plan.row_for('A')
        self.assertEqual((row['B'], row['C'], row[PlanOutcome.NEVER]),
                         (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4)))
        self.assertTrue(all(sum(plan.row_for(station).values()) == 1 for station in plan.stations))

    def test_no_observed_departure(self):
        row = self.freeze('no_departure').row_for('A')
        self.assertEqual(row, {
            'A': Fraction(0), PlanOutcome.RELEASE: Fraction(0),
            PlanOutcome.REJECT: Fraction(0), PlanOutcome.NEVER: Fraction(1),
        })

    def test_private_cycle_preserves_first_exit(self):
        row = self.freeze('private_cycle').row_for('A')
        # On each visit to the gate, 1/2 goes to B, 1/4 rejects, and 1/4 retries.
        self.assertEqual(row['B'], Fraction(2, 3))
        self.assertEqual(row[PlanOutcome.REJECT], Fraction(1, 3))
        self.assertEqual(row[PlanOutcome.NEVER], Fraction(0))

    def test_snapshot_round_trip(self):
        plan = self.freeze('returning')
        self.source.close()
        self.reopen_archive()
        restored = load_plan(self.archive, plan.plan_id)
        self.assertEqual(restored, plan)
        self.assertEqual(restored.revision_id, 1)
        self.assertEqual(restored.stations, ('A', 'C', 'B'))
        self.assertEqual(tuple(restored.row_for('A')), ('A', 'C', 'B', *PlanOutcome))
        self.assertEqual(restored.row_for('A')['B'], Fraction(1, 4))
        payload, = self.archive.execute(
            'SELECT payload FROM fixed_plans WHERE plan_id = ?', (plan.plan_id,)
        ).fetchone()
        self.assertNotIn('private-gate', payload)
        self.assertNotIn('private-hold', payload)
        self.assertNotIn('passed-bench', payload)
        self.assertNotIn('counts', payload)

    def test_unknown_terminal(self):
        with self.assertRaises(InvalidCounts):
            receive(self.source, 'invalid', [Station('A', True)], 'pass', 'fail',
                    [TransferCount('A', 'undeclared', 1)])
        self.assertEqual(self.revision_ids(), [])

    def test_late_unknown_endpoint(self):
        data = sample('straight')
        data['counts'].append(['C', 'not-a-terminal', 8])
        with self.assertRaises(InvalidCounts):
            receive_sample(self.source, data)
        self.assertEqual(self.revision_ids(), [])
        data['counts'].pop()
        revision_id = receive_sample(self.source, data)
        self.assertEqual(revision_id, 1)
        loaded = load_revision(self.source, revision_id)
        self.assertEqual(loaded.counts, tuple(TransferCount(*row) for row in data['counts']))

    def test_batch_conflict(self):
        data = sample('straight')
        revision_id = receive_sample(self.source, data)
        original = load_revision(self.source, revision_id)
        data['counts'][0][2] = 9
        with self.assertRaises(BatchConflict):
            receive_sample(self.source, data)
        self.assertEqual(self.revision_ids(), [revision_id])
        self.assertEqual(load_revision(self.source, revision_id), original)

    def test_unreadable_revision(self):
        revision_id = receive_sample(self.source, sample('straight'))
        with self.assertRaises(FreezeError):
            freeze_plan(self.source, self.archive, revision_id + 1)
        self.source.close()
        with self.assertRaises(FreezeError):
            freeze_plan(self.source, self.archive, revision_id)
        with self.assertRaises(PlanNotFound):
            load_plan(self.archive, 1)
        self.reopen_source()
        self.assertEqual(freeze_plan(self.source, self.archive, revision_id).plan_id, 1)

    def test_duplicate_observations_and_large_counts(self):
        large = 1 << 15000
        rows = [TransferCount('A', 'pass', 1), TransferCount('A', 'pass', large),
                TransferCount('A', 'fail', large)]
        revision_id = receive(self.source, 'large', [Station('A', True)], 'pass', 'fail', rows)
        self.assertEqual(load_revision(self.source, revision_id).counts, tuple(rows))
        plan = freeze_plan(self.source, self.archive, revision_id)
        self.reopen_archive()
        row = load_plan(self.archive, plan.plan_id).row_for('A')
        self.assertEqual(row[PlanOutcome.RELEASE], Fraction(large + 1, 2 * large + 1))
        self.assertEqual(row[PlanOutcome.REJECT], Fraction(large, 2 * large + 1))
