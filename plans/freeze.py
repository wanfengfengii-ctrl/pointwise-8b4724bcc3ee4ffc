"""Freeze an audited public plan from one committed source revision."""

import sqlite3

from plans.balance import validate_transfer_ledger
from plans.catalog import save_plan
from plans.transfer import build_transfer_rows
from source.revisions import RevisionNotFound, load_revision
from source.validation import validate_batch


class FreezeError(ValueError):
    pass


def freeze_plan(source, archive, revision_id):
    try:
        revision = load_revision(source, revision_id)
        validate_batch(revision.batch, revision.stations, revision.release, revision.reject, revision.counts)
        stations = tuple(station.name for station in revision.stations if station.public)
        ledger = build_transfer_rows(revision)
        validate_transfer_ledger(stations, ledger)
        rows = tuple(tuple(ledger[station].values()) for station in stations)
        return save_plan(archive, revision.revision_id, stations, rows)
    except (RevisionNotFound, sqlite3.Error, ValueError, TypeError) as error:
        raise FreezeError(f'could not freeze source revision {revision_id!r}') from error
