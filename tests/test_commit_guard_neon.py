"""Actual passage across the commit freshness boundary in isolated Neon only."""

from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from services.domain.contracts import content_hash
from services.storage import jobs
from services.storage.database import database
from tests.test_release_storage import fresh_assertion, seed


def test_capture_fresh_at_insert_cannot_commit_after_sixty_seconds(neon_store):
    url, schema = neon_store
    with database(url, schema=schema) as c:
        owner, rid, session, approval, capture, *_ = seed(c)
    with (
        pytest.raises(psycopg.errors.RaiseException, match="evidence expired"),
        database(url, schema=schema) as c,
    ):
        attempt, _ = fresh_assertion(c, owner, rid, session, approval, capture, commit_stale=True)
        value = {"scope": "Commit guard assertion only"}
        c.execute(
            "INSERT INTO receipts VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                attempt.id,
                rid,
                owner,
                approval.id,
                Jsonb(value),
                content_hash(value),
                jobs.clock(c),
            ),
        )
        # Constraint is initially deferred: insertion succeeds, then actual COMMIT rejects
        # the expired captured interval. No assertion receipt survives this transaction.
        assert c.execute("SELECT count(*) AS n FROM receipts").fetchone()["n"] == 1
    with database(url, schema=schema) as c:
        assert c.execute("SELECT count(*) AS n FROM receipts").fetchone()["n"] == 0
