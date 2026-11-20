"""Freeze a V2 two-stage review plan from one committed source revision."""

import sqlite3

from plans.catalog import save_review_plan
from plans.freeze import FreezeError
from plans.review_balance import validate_review_ledger
from plans.review_transfer import build_review_rows
from source.revisions import RevisionNotFound, load_revision
from source.validation import validate_batch, validate_labels


def freeze_review_plan(source, archive, revision_id):
    try:
        revision = load_revision(source, revision_id)
        validate_batch(
            revision.batch, revision.stations, revision.release,
            revision.reject, revision.counts,
        )
        validate_labels(revision.stations, revision.labels, allow_clear=False)
        stations, rows = build_review_rows(revision)
        validate_review_ledger(stations, rows)
        return save_review_plan(archive, revision.revision_id, stations, rows)
    except (RevisionNotFound, sqlite3.Error, ValueError, TypeError) as error:
        raise FreezeError(f'could not freeze review source revision {revision_id!r}') from error
