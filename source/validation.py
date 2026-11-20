"""Rules shared by batch intake, corrections, and revision export."""

from source.revisions import Station, TransferCount


class InvalidCounts(ValueError):
    pass


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
