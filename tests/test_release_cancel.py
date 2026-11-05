"""Cancel after capture completion but before commit must stop an internal receipt."""

from services.storage import decisions, releases
from services.storage.database import database
from tests.test_release_storage import fresh_assertion, seed


def test_completed_recheck_can_be_cancelled_before_internal_commit(neon_store):
    url, schema = neon_store
    with database(url, schema=schema) as c:
        owner, rid, session, approval, capture, *_ = seed(c)
        assert decisions.state(c, owner, rid).comparison.sources[0].rank == 1
        attempt, _ = fresh_assertion(c, owner, rid, session, approval, capture)
        result = releases.cancel(c, owner, attempt.id)
        assert result.state == "blocked" and result.reason == "RELEASE_CANCELLED"
        assert releases.cancel(c, owner, attempt.id) == result
        releases.finalize(c, attempt.id)
        assert c.execute("SELECT count(*) AS n FROM receipts").fetchone()["n"] == 0
