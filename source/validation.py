"""Rules shared by batch intake, corrections, and revision export."""

from collections.abc import Mapping

from source.revisions import Station, TransferCount


class InvalidCounts(ValueError):
    pass


REVIEW_LABELS = frozenset(('recheck', 'witness', 'reset'))


def _identifier(value):
    return type(value) is str and bool(value.strip())


def _records(values, label):
    try:
        return tuple(values)
    except TypeError as error:
        raise InvalidCounts(f'{label} must be a sequence of records') from error


def validate_counts(stations, release, reject, counts):
    rows = _records(counts, 'counts')
    origins = {station.name for station in stations}
    destinations = origins | {release, reject}
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, TransferCount):
            raise InvalidCounts(f'count row {position} is not a TransferCount')
        if not _identifier(row.origin) or row.origin not in origins:
            raise InvalidCounts(f'unknown origin in count row {position}')
        if not _identifier(row.destination) or row.destination not in destinations:
            raise InvalidCounts(f'unknown destination in count row {position}')
        if type(row.count) is not int or row.count < 0:
            raise InvalidCounts(f'count row {position} requires a nonnegative integer')
    return rows


def validate_batch(batch, stations, release, reject, counts):
    if not _identifier(batch):
        raise InvalidCounts('a batch identifier is required')
    stations = _records(stations, 'stations')
    names = set()
    for station in stations:
        if not isinstance(station, Station) or not _identifier(station.name):
            raise InvalidCounts('each station requires a name')
        if type(station.public) is not bool:
            raise InvalidCounts(f'invalid visibility for station {station.name}')
        if station.name in names:
            raise InvalidCounts(f'duplicate station {station.name}')
        names.add(station.name)
    if not 1 <= sum(station.public for station in stations) <= 6:
        raise InvalidCounts('declare one to six public stations')
    if not _identifier(release) or not _identifier(reject):
        raise InvalidCounts('declare release and reject terminals')
    if release == reject or release in names or reject in names:
        raise InvalidCounts('the terminal and station identities must be distinct')
    return stations, validate_counts(stations, release, reject, counts)


def validate_labels(stations, labels, *, allow_clear):
    """Validate a station-to-review-label mapping.

    Intake only accepts concrete labels; corrections may also use ``None`` to
    clear a label registered on the parent revision. Terminals can never carry
    a label because they are not declared stations.
    """
    if labels is None:
        return {}
    if not isinstance(labels, Mapping):
        raise InvalidCounts('labels must be a mapping of station names to review labels')
    names = {station.name for station in stations}
    normalized = {}
    for name, kind in labels.items():
        if type(name) is not str or name not in names:
            raise InvalidCounts(f'unknown station {name!r} in labels')
        if kind is None:
            if not allow_clear:
                raise InvalidCounts(f'station {name} requires a concrete review label')
            normalized[name] = None
        elif type(kind) is not str or kind not in REVIEW_LABELS:
            raise InvalidCounts(f'unknown review label {kind!r} for station {name}')
        else:
            normalized[name] = kind
    return normalized


def merge_labels(parent_labels, patch):
    """Apply an exact correction patch over the parent's label mapping."""
    merged = dict(parent_labels)
    for name, kind in patch.items():
        if kind is None:
            merged.pop(name, None)
        else:
            merged[name] = kind
    return merged
