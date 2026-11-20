from source.corrections import amend
from source.intake import BatchConflict, receive
from source.revisions import Station, TransferCount, load_revision
from source.validation import InvalidCounts
from tests.fixtures import DatabaseCase


LABELED_STATIONS = (
    Station('A', True), Station('B', True),
    Station('P', False), Station('Q', False), Station('R', False),
)


def _receive(source, labels=None):
    return receive(
        source, 'labels', LABELED_STATIONS, 'pass', 'fail',
        (
            TransferCount('A', 'P', 1), TransferCount('P', 'Q', 1),
            TransferCount('Q', 'B', 1), TransferCount('B', 'pass', 1),
            TransferCount('B', 'R', 1), TransferCount('R', 'B', 1),
        ),
        labels=labels,
    )


class TestLabels(DatabaseCase):
    def test_receive_registers_labels(self):
        revision_id = _receive(self.source, {'P': 'recheck', 'Q': 'witness', 'R': 'reset'})
        revision = load_revision(self.source, revision_id)
        self.assertEqual(revision.labels, {'P': 'recheck', 'Q': 'witness', 'R': 'reset'})

    def test_labels_default_to_empty_for_old_and_new_revisions(self):
        revision_id = _receive(self.source)
        self.assertEqual(load_revision(self.source, revision_id).labels, {})

    def test_private_and_public_stations_may_carry_labels(self):
        revision_id = _receive(self.source, {'A': 'recheck', 'R': 'reset'})
        self.assertEqual(load_revision(self.source, revision_id).labels,
                         {'A': 'recheck', 'R': 'reset'})

    def test_unknown_station_label_is_rejected_without_a_revision(self):
        before = self.revision_ids()
        for labels in ({'missing': 'recheck'}, {42: 'reset'}, {'P': 42},
                       {'P': 'rework'}, {'P': None}, 'recheck'):
            with self.subTest(labels=labels):
                with self.assertRaises(InvalidCounts):
                    _receive(self.source, labels)
        self.assertEqual(self.revision_ids(), before)

    def test_amend_inherits_replaces_and_clears_labels(self):
        parent = _receive(self.source, {'P': 'recheck', 'Q': 'witness', 'R': 'reset'})
        child = amend(
            self.source, parent, [TransferCount('B', 'pass', 2)],
            labels={'Q': 'recheck', 'R': None},
        )
        revision = load_revision(self.source, child)
        self.assertEqual(revision.labels, {'P': 'recheck', 'Q': 'recheck'})
        # The parent revision is untouched.
        self.assertEqual(load_revision(self.source, parent).labels,
                         {'P': 'recheck', 'Q': 'witness', 'R': 'reset'})

    def test_label_only_amend_keeps_counts(self):
        parent = _receive(self.source, {'P': 'recheck', 'R': 'reset'})
        original = load_revision(self.source, parent)
        child = amend(self.source, parent, [], labels={'R': None})
        revised = load_revision(self.source, child)
        self.assertEqual(revised.counts, original.counts)
        self.assertEqual(revised.labels, {'P': 'recheck'})
        self.assertEqual(revised.parent_id, parent)

    def test_invalid_amend_labels_change_nothing(self):
        parent = _receive(self.source, {'P': 'recheck'})
        before = self.revision_ids()
        for labels in ({'P': 'rework'}, {'missing': 'reset'}, {'P': 'recheck', 'Q': 9}):
            with self.subTest(labels=labels):
                with self.assertRaises(InvalidCounts):
                    amend(self.source, parent, [], labels=labels)
        self.assertEqual(self.revision_ids(), before)

    def test_terminal_cannot_be_labeled(self):
        with self.assertRaises(InvalidCounts):
            receive(
                self.source, 'terminal-label', (Station('A', True),), 'pass', 'fail',
                (TransferCount('A', 'pass', 1),), labels={'pass': 'recheck'},
            )
        self.assertEqual(self.revision_ids(), [])

    def test_labels_round_trip_after_reopen(self):
        revision_id = _receive(self.source, {'P': 'recheck', 'Q': 'witness'})
        self.reopen_source()
        self.assertEqual(
            load_revision(self.source, revision_id).labels,
            {'P': 'recheck', 'Q': 'witness'},
        )

    def test_batch_conflict_still_rejects_duplicate_intake(self):
        _receive(self.source)
        with self.assertRaises(BatchConflict):
            _receive(self.source)
