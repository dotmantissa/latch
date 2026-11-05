"""Neon Postgres: pooled application traffic, direct transactional migrations."""

import hashlib
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

SCHEMA_VERSION = 2


def migrations() -> list[tuple[int, str, str]]:
    """Numbered immutable scripts; never silently accept gaps or changed history."""
    result = []
    for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
        match = re.fullmatch(r"([0-9]{3})_[a-z0-9_]+\.sql", path.name)
        if match is None:
            raise RuntimeError("Invalid migration filename")
        script = path.read_text()
        result.append((int(match[1]), script, hashlib.sha256(script.encode()).hexdigest()))
    if [row[0] for row in result] != list(range(1, SCHEMA_VERSION + 1)):
        raise RuntimeError("Migration history is not contiguous")
    return result


def verify_history(rows, *, complete: bool) -> None:
    expected = [(version, checksum) for version, _, checksum in migrations()]
    actual = [(row["version"], row["checksum"]) for row in rows]
    if actual != expected[: len(actual)] or len(actual) > len(expected):
        raise RuntimeError("Unknown schema or changed migration checksum")
    if complete and actual != expected:
        raise RuntimeError("Database schema is not supported; run operator migrations")


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
            rows = conn.execute(
                "SELECT version,checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            verify_history(rows, complete=True)
        yield conn


def initialize(url: str, *, schema: str = "latch", target_version: int = SCHEMA_VERSION) -> None:
    if type(target_version) is not int or not 1 <= target_version <= SCHEMA_VERSION:
        raise ValueError("Invalid migration target")
    scripts = migrations()
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
        verify_history(rows, complete=False)
        if len(rows) > target_version:
            raise RuntimeError("Migration downgrade is not supported")
        for version, script, checksum in scripts[len(rows) : target_version]:
            conn.execute(script, prepare=False)
            conn.execute(
                "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)",
                (version, checksum),
            )


def lock_owner(conn, owner_id: str) -> None:
    """Serialize an owner's idempotent commands without locking other owners."""
    conn.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (owner_id,))
