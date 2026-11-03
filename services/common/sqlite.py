"""The explicitly linked SQLite runtime; fail before opening an unsafe database."""

import sqlite3
from pathlib import Path

MINIMUM_SQLITE = (3, 51, 3)


def assert_runtime() -> str:
    if sqlite3.sqlite_version_info < MINIMUM_SQLITE:
        raise RuntimeError("SQLite 3.51.3 or newer is required for the WAL fix")
    return sqlite3.sqlite_version


def connect(path: Path) -> sqlite3.Connection:
    assert_runtime()
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=5000")
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise RuntimeError("The database must use WAL on local writable storage")
        return connection
    except Exception:
        connection.close()
        raise
