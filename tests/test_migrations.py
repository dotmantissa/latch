"""Immutable cumulative migration history, including a real populated isolated upgrade."""

from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from services.storage.database import database, direct_url, initialize, migrations, verify_history


def test_history_rejects_gaps_tampering_and_downgrade():
    rows = [{"version": v, "checksum": h} for v, _, h in migrations()]
    verify_history(rows, complete=True)
    verify_history(rows[:1], complete=False)
    for invalid in (
        rows[1:],
        rows + [{"version": 3, "checksum": "unknown"}],
        [dict(rows[0], checksum="tampered")],
    ):
        with pytest.raises(RuntimeError):
            verify_history(invalid, complete=False)
    with pytest.raises(RuntimeError):
        verify_history(rows[:1], complete=True)


def test_actual_v1_upgrade_preserves_records_and_refuses_checksum_changes(neon_store):
    url, _ = neon_store
    schema = "latch_test_" + uuid4().hex
    try:
        initialize(url, schema=schema, target_version=1)
        user = uuid4()
        with database(url, schema=schema, check_schema=False) as c:
            c.execute(
                "INSERT INTO users VALUES(%s,'upgrade_owner','Assertion','unused',true,1,1)",
                (user,),
            )
        initialize(url, schema=schema)
        initialize(url, schema=schema)
        with database(url, schema=schema) as c:
            assert c.execute("SELECT id FROM users").fetchone()["id"] == user
            c.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
        with pytest.raises(RuntimeError):
            initialize(url, schema=schema)
        with pytest.raises(RuntimeError), database(url, schema=schema):
            pass
    finally:
        with psycopg.connect(direct_url(url), connect_timeout=10) as c:
            c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
