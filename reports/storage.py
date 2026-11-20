"""Archive lifecycle, transaction boundaries, and ordered record access."""

import sqlite3
from contextlib import contextmanager

from plans.catalog import initialize_plan_catalog


_SCHEMA = """
CREATE TABLE IF NOT EXISTS formal_reports (
    report_id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES fixed_plans(plan_id),
    payload TEXT NOT NULL,
    UNIQUE (report_id, plan_id)
);
CREATE TABLE IF NOT EXISTS handover_entries (
    report_id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL,
    start TEXT NOT NULL,
    FOREIGN KEY (report_id, plan_id) REFERENCES formal_reports(report_id, plan_id)
);
CREATE INDEX IF NOT EXISTS handover_by_plan ON handover_entries(plan_id, report_id);
"""


def initialize_archive(connection):
    if connection.in_transaction:
        raise sqlite3.ProgrammingError('initialize_archive requires an idle connection')
    connection.execute('PRAGMA foreign_keys = ON')
    initialize_plan_catalog(connection)
    connection.executescript(_SCHEMA)


def open_archive(path):
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        initialize_archive(connection)
    except BaseException:
        connection.close()
        raise
    return connection


@contextmanager
def publication_transaction(connection):
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def insert_report(connection, plan_id, payload):
    cursor = connection.execute(
        'INSERT INTO formal_reports(plan_id, payload) VALUES (?, ?)', (plan_id, payload)
    )
    return cursor.lastrowid


def insert_handover_entry(connection, report_id, plan_id, start):
    connection.execute(
        'INSERT INTO handover_entries(report_id, plan_id, start) VALUES (?, ?, ?)',
        (report_id, plan_id, start),
    )


def load_report_row(connection, report_id):
    if type(report_id) is not int or not 0 < report_id < 2**63:
        return None
    return connection.execute(
        'SELECT report_id, plan_id, payload FROM formal_reports WHERE report_id = ?', (report_id,)
    ).fetchone()


def list_handover_rows(connection, plan_id):
    return connection.execute(
        'SELECT report_id, start FROM handover_entries WHERE plan_id = ? ORDER BY report_id',
        (plan_id,),
    ).fetchall()
