from fractions import Fraction

from plans.catalog import PlanNotFound
from plans.freeze import freeze_plan
from plans.snapshot import PlanOutcome
from source.intake import receive
from source.revisions import Station, TransferCount
from tests.fixtures import DatabaseCase
from walks.replay import replay_walk
from walks.session import InvalidWalk


class TestWalk(DatabaseCase):
    def test_return_erases_suffix(self):
        plan = self.freeze('returning')
        result = replay_walk(self.archive, plan.plan_id, 'A', ('B', 'A', 'C', PlanOutcome.RELEASE))
        self.assertEqual(result.plan_id, plan.plan_id)
        self.assertEqual(result.actual, ('A', 'B', 'A', 'C'))
        self.assertEqual(result.retained, ('A', 'C'))
        self.assertEqual(result.erasures, (('A', ('B',)),))
        self.assertEqual(result.retained_handoffs, (('A', 'C'),))
        self.assertIs(result.terminal, PlanOutcome.RELEASE)

    def test_public_self_return(self):
        plan = self.freeze('self_walk')
        observed = replay_walk(self.archive, plan.plan_id, 'A', ('A', PlanOutcome.RELEASE))
        self.assertEqual(observed.actual, ('A', 'A'))
        self.assertEqual(observed.retained, ('A',))
        self.assertEqual(observed.erasures, (('A', ()),))
        self.assertEqual(observed.retained_handoffs, ())

    def test_impossible_step(self):
        plan = self.freeze('zero')
        with self.assertRaises(InvalidWalk):
            replay_walk(self.archive, plan.plan_id, 'A', ('B', PlanOutcome.RELEASE))

    def test_zero_with_other_exit(self):
        plan = self.freeze('zero')
        row = plan.row_for('A')
        self.assertEqual(row['B'], Fraction(0))
        self.assertEqual(row['C'], Fraction(1))
        with self.assertRaises(InvalidWalk):
            replay_walk(self.archive, plan.plan_id, 'A', ('B', PlanOutcome.RELEASE))
        valid = replay_walk(self.archive, plan.plan_id, 'A', ('C', PlanOutcome.RELEASE))
        self.assertEqual(valid.retained, ('A', 'C'))

    def test_after_terminal(self):
        plan = self.freeze('straight')
        with self.assertRaises(InvalidWalk):
            replay_walk(self.archive, plan.plan_id, 'A', ('B', PlanOutcome.RELEASE, 'A'))

    def test_missing_terminal(self):
        plan = self.freeze('no_departure')
        with self.assertRaises(InvalidWalk):
            replay_walk(self.archive, plan.plan_id, 'A', ())
        valid = replay_walk(self.archive, plan.plan_id, 'A', (PlanOutcome.NEVER,))
        self.assertIs(valid.terminal, PlanOutcome.NEVER)
        self.assertEqual(valid.actual, ('A',))

    def test_plan_and_start_validation(self):
        plan = self.freeze('straight')
        with self.assertRaises(InvalidWalk):
            replay_walk(self.archive, plan.plan_id, 'outside', (PlanOutcome.RELEASE,))
        with self.assertRaises(PlanNotFound):
            replay_walk(self.archive, plan.plan_id + 1, 'A', (PlanOutcome.RELEASE,))

    def test_public_identity_is_distinct_from_terminal_token(self):
        revision = receive(
            self.source, 'tokens', (Station('A', True), Station('release', True)), 'pass', 'fail',
            (TransferCount('A', 'release', 1), TransferCount('release', 'pass', 1)),
        )
        plan = freeze_plan(self.source, self.archive, revision)
        with self.assertRaises(InvalidWalk):
            replay_walk(self.archive, plan.plan_id, 'A', (PlanOutcome.RELEASE,))
        result = replay_walk(self.archive, plan.plan_id, 'A', ('release', PlanOutcome.RELEASE))
        self.assertEqual(result.retained, ('A', 'release'))
