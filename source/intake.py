"""Accept a complete bench batch under its original batch identity."""

from source.revisions import insert_revision
from source.storage import revision_transaction
from source.validation import validate_batch


class BatchConflict(ValueError):
    pass


def receive(connection, batch, stations, release, reject, counts):
    stations, counts = validate_batch(batch, stations, release, reject, counts)
    with revision_transaction(connection):
        existing = connection.execute(
            'SELECT revision_id FROM revisions WHERE batch = ? AND parent_id IS NULL',
            (batch,),
        ).fetchone()
        if existing is not None:
            raise BatchConflict(batch)
        return insert_revision(connection, batch, None, stations, release, reject, counts)
