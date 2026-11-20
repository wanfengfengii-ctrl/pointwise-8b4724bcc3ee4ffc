"""Plan numbering and immutable plan records in the archive database."""

from plans.snapshot import FixedPlan, decode_plan, encode_plan


class PlanNotFound(LookupError):
    pass


def initialize_plan_catalog(connection):
    connection.execute(
        'CREATE TABLE IF NOT EXISTS fixed_plans ('
        'plan_id INTEGER PRIMARY KEY, revision_id INTEGER NOT NULL, payload TEXT NOT NULL)'
    )


def save_plan(connection, revision_id, stations, rows):
    payload = encode_plan(stations, rows)
    connection.execute('BEGIN IMMEDIATE')
    try:
        cursor = connection.execute(
            'INSERT INTO fixed_plans(revision_id, payload) VALUES (?, ?)',
            (revision_id, payload),
        )
        plan = FixedPlan(cursor.lastrowid, revision_id, stations, rows)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return plan


def load_plan(connection, plan_id):
    if type(plan_id) is not int or not 0 < plan_id < 2**63:
        raise PlanNotFound(plan_id)
    result = connection.execute(
        'SELECT revision_id, payload FROM fixed_plans WHERE plan_id = ?', (plan_id,)
    ).fetchone()
    if result is None:
        raise PlanNotFound(plan_id)
    revision_id, payload = result
    return decode_plan(plan_id, revision_id, payload)
