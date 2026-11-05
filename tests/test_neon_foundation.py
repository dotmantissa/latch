"""Actual PostgreSQL constraints, transactional migrations and isolation."""

from uuid import uuid4

import psycopg
import pytest

from services.storage.database import SCHEMA_VERSION, database, initialize


def test_migration_is_repeatable_and_versions_immutable(neon_store):
    url, schema = neon_store
    initialize(url, schema=schema)
    user, request = uuid4(), uuid4()
    with database(url, schema=schema) as conn:
        conn.execute(
            "INSERT INTO users VALUES(%s,'schema_assertion','Assertion','unused',true,1,1)", (user,)
        )
        conn.execute(
            (
                "INSERT INTO requests(id,owner_id,current_version,created_at,updated_at"
                ") VALUES(%s,%s,1,1,1)"
            ),
            (request, user),
        )
        conn.execute("INSERT INTO request_versions VALUES(%s,1,'{}','assertion',1)", (request,))
    with pytest.raises(psycopg.errors.RaiseException), database(url, schema=schema) as conn:
        conn.execute(
            "UPDATE request_versions SET content_hash='changed' WHERE request_id=%s", (request,)
        )
    with database(url, schema=schema) as conn:
        assert (
            conn.execute(
                "SELECT content_hash FROM request_versions WHERE request_id=%s", (request,)
            ).fetchone()["content_hash"]
            == "assertion"
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), database(url, schema=schema) as conn:
        conn.execute(
            (
                "INSERT INTO events(owner_id,request_id,kind,safe_payload_json,at) "
                "VALUES(%s,%s,'assertion','{}',1)"
            ),
            (uuid4(), request),
        )


def test_transaction_rollback_and_newer_schema_refusal(neon_store):
    url, schema = neon_store
    with pytest.raises(RuntimeError), database(url, schema=schema) as conn:
        conn.execute(
            "INSERT INTO users VALUES(%s,'rollback_assertion','Assertion','unused',true,1,1)",
            (uuid4(),),
        )
        raise RuntimeError("Rollback assertion")
    with database(url, schema=schema) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS count FROM users WHERE username='rollback_assertion'"
            ).fetchone()["count"]
            == 0
        )
        conn.execute(
            "INSERT INTO schema_migrations(version,checksum) VALUES(%s,'unknown')",
            (SCHEMA_VERSION + 1,),
        )
    try:
        with pytest.raises(RuntimeError):
            initialize(url, schema=schema)
        with pytest.raises(RuntimeError), database(url, schema=schema):
            pass
    finally:
        with database(url, schema=schema, check_schema=False) as conn:
            conn.execute("DELETE FROM schema_migrations WHERE version=%s", (SCHEMA_VERSION + 1,))
