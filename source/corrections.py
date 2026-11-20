"""Apply corrections to a named parent while retaining its original evidence."""

from source.revisions import insert_revision, load_revision
from source.storage import revision_transaction
from source.validation import InvalidCounts, validate_counts


def apply_count_replacements(parent, replacements):
    replacements = validate_counts(parent.stations, parent.release, parent.reject, replacements)
    pending = {row.key: row for row in replacements}
    if len(pending) != len(replacements):
        raise InvalidCounts('supply at most one replacement for each directed key')
    replaced_keys = set(pending)
    merged = []
    for row in parent.counts:
        if row.key in pending:
            merged.append(pending.pop(row.key))
        elif row.key not in replaced_keys:
            merged.append(row)
    merged.extend(pending.values())
    return tuple(merged)


def amend(connection, parent_id, replacements):
    with revision_transaction(connection):
        parent = load_revision(connection, parent_id)
        counts = apply_count_replacements(parent, replacements)
        return insert_revision(
            connection, parent.batch, parent.revision_id, parent.stations,
            parent.release, parent.reject, counts,
        )
