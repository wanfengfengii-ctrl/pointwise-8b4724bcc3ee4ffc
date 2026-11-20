"""Source database lifecycle and revision write transactions."""

import sqlite3
from contextlib import contextmanager


_SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (
    revision_id INTEGER PRIMARY KEY,
    batch TEXT NOT NULL,
    parent_id INTEGER REFERENCES revisions(revision_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS received_batch
    ON revisions(batch) WHERE parent_id IS NULL;
CREATE TABLE IF NOT EXISTS stations (
    revision_id INTEGER NOT NULL REFERENCES revisions(revision_id),
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL,
    is_public INTEGER NOT NULL CHECK (is_public IN (0, 1)),
    PRIMARY KEY (revision_id, ordinal),
    UNIQUE (revision_id, name)
);
CREATE TABLE IF NOT EXISTS terminals (
    revision_id INTEGER NOT NULL REFERENCES revisions(revision_id),
    disposition TEXT NOT NULL CHECK (disposition IN ('release', 'reject')),
    name TEXT NOT NULL,
    PRIMARY KEY (revision_id, disposition),
    UNIQUE (revision_id, name)
);
CREATE TABLE IF NOT EXISTS transfer_counts (
    revision_id INTEGER NOT NULL REFERENCES revisions(revision_id),
    ordinal INTEGER NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    count_hex TEXT NOT NULL,
    PRIMARY KEY (revision_id, ordinal),
    FOREIGN KEY (revision_id, origin) REFERENCES stations(revision_id, name)
);
"""


def initialize_source(connection):
    if connection.in_transaction:
        raise sqlite3.ProgrammingError('initialize_source requires an idle connection')
    connection.execute('PRAGMA foreign_keys = ON')
    connection.executescript(_SCHEMA)


def open_source(path):
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        initialize_source(connection)
    except BaseException:
        connection.close()
        raise
    return connection


@contextmanager
def revision_transaction(connection):
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
