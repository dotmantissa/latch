"""Opt-in real Neon integration schemas, created and dropped by exact generated name."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from services.common.config import read_secret
from services.storage.database import direct_url, initialize


class PrivateURL(str):
    def __repr__(self):
        return "<private database connection>"


@pytest.fixture(scope="module")
def neon_store():
    path = os.getenv("LATCH_TEST_DATABASE_URL_FILE")
    if not path:
        pytest.skip("Set LATCH_TEST_DATABASE_URL_FILE to run real Neon integration checks")
    url = PrivateURL(read_secret(Path(path)))
    schema = "latch_test_" + uuid4().hex
    recovery = Path("var/test-schemas")
    recovery.mkdir(parents=True, exist_ok=True, mode=0o700)
    note = recovery / schema
    note.write_text(schema)
    try:
        initialize(url, schema=schema)
        yield url, schema
    finally:
        with psycopg.connect(direct_url(url), connect_timeout=10) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        note.unlink()
