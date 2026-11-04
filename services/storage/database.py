"""Neon Postgres: pooled application traffic, direct transactional migrations."""

import hashlib
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

SCHEMA_VERSION = 1


def direct_url(url: str) -> str:
    info = conninfo_to_dict(url)
    host = info.get("host", "")
    if host.endswith(".neon.tech"):
        info["host"] = host.replace("-pooler.", ".", 1)
    return make_conninfo(**info)


@contextmanager
def database(url: str, *, schema: str = "latch", check_schema: bool = True):
    if not re.fullmatch(r"latch(?:_test_[a-f0-9]{32})?", schema):
        raise ValueError("Invalid application schema")
    with psycopg.connect(
        url, connect_timeout=10, prepare_threshold=None, row_factory=dict_row
    ) as conn:
        # No session state on PgBouncer: all settings are transaction-local.
        conn.execute(
            sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema))
        )
        conn.execute("SET LOCAL statement_timeout = '10s'")
        conn.execute("SET LOCAL lock_timeout = '5s'")
        if check_schema:
            row = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if row is None or row["version"] != SCHEMA_VERSION:
                raise RuntimeError("Database schema is not supported; run operator migrations")
        yield conn


def initialize(url: str, *, schema: str = "latch") -> None:
    script = (Path(__file__).parent / "migrations/001_foundation.sql").read_text()
    checksum = hashlib.sha256(script.encode()).hexdigest()
    with database(direct_url(url), schema=schema, check_schema=False) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"latch-migration:{schema}",))
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY "
            "KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT "
            "now())"
        )
        rows = conn.execute(
            "SELECT version,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        if rows:
            if (
                len(rows) != 1
                or rows[0]["version"] != SCHEMA_VERSION
                or rows[0]["checksum"] != checksum
            ):
                raise RuntimeError("Unknown schema or changed migration checksum")
            return
        conn.execute(script, prepare=False)
        conn.execute(
            "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)",
            (SCHEMA_VERSION, checksum),
        )


def lock_owner(conn, owner_id: str) -> None:
    """Serialize an owner's idempotent commands without locking other owners."""
    conn.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (owner_id,))
