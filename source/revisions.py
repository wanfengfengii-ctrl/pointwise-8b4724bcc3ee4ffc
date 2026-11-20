"""Immutable source records and their lossless SQLite representation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Station:
    name: str
    public: bool


@dataclass(frozen=True, slots=True)
class TransferCount:
    origin: str
    destination: str
    count: int

    @property
    def key(self):
        return self.origin, self.destination


@dataclass(frozen=True, slots=True)
class Revision:
    revision_id: int
    batch: str
    parent_id: int | None
    stations: tuple[Station, ...]
    release: str
    reject: str
    counts: tuple[TransferCount, ...]


class RevisionNotFound(LookupError):
    pass


def insert_revision(connection, batch, parent_id, stations, release, reject, counts):
    """Insert a validated snapshot inside the caller's revision transaction."""
    cursor = connection.execute(
        'INSERT INTO revisions(batch, parent_id) VALUES (?, ?)', (batch, parent_id)
    )
    revision_id = cursor.lastrowid
    connection.executemany(
        'INSERT INTO stations VALUES (?, ?, ?, ?)',
        ((revision_id, pos, station.name, int(station.public))
         for pos, station in enumerate(stations)),
    )
    connection.executemany(
        'INSERT INTO terminals VALUES (?, ?, ?)',
        ((revision_id, 'release', release), (revision_id, 'reject', reject)),
    )
    # Hex text preserves Python integers beyond SQLite's signed integer range.
    connection.executemany(
        'INSERT INTO transfer_counts VALUES (?, ?, ?, ?, ?)',
        ((revision_id, pos, row.origin, row.destination, format(row.count, 'x'))
         for pos, row in enumerate(counts)),
    )
    return revision_id


def load_revision(connection, revision_id):
    if type(revision_id) is not int or not 0 < revision_id < 2**63:
        raise RevisionNotFound(revision_id)
    key = (revision_id,)
    header = connection.execute(
        'SELECT batch, parent_id FROM revisions WHERE revision_id = ?', key
    ).fetchone()
    if header is None:
        raise RevisionNotFound(revision_id)
    batch, parent_id = header
    stations = tuple(
        Station(name, bool(public))
        for name, public in connection.execute(
            'SELECT name, is_public FROM stations WHERE revision_id = ? ORDER BY ordinal', key
        )
    )
    terminals = dict(connection.execute(
        'SELECT disposition, name FROM terminals WHERE revision_id = ?', key
    ))
    if terminals.keys() != {'release', 'reject'}:
        raise ValueError(f'incomplete terminal definitions in revision {revision_id}')
    counts = tuple(
        TransferCount(origin, destination, int(count, 16))
        for origin, destination, count in connection.execute(
            'SELECT origin, destination, count_hex FROM transfer_counts '
            'WHERE revision_id = ? ORDER BY ordinal', key
        )
    )
    return Revision(
        revision_id, batch, parent_id, stations, terminals['release'], terminals['reject'], counts
    )
