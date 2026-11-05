"""Real Neon queue transactions and fencing; source-world correctness is a separate gate."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from services.api.errors import ApiError
from services.storage import jobs
from services.storage.database import database


@pytest.fixture(scope="module")
def queue(neon_store):
    url, schema = neon_store
    owner, other, source_profile = uuid4(), uuid4(), "queue_assertion"
    with database(url, schema=schema) as c:
        c.execute(
            "INSERT INTO users VALUES(%s,'queue_owner','Assertion','unused',true,1,1)", (owner,)
        )
        c.execute(
            "INSERT INTO users VALUES(%s,'queue_other','Assertion','unused',true,1,1)", (other,)
        )
        c.execute(
            "INSERT INTO source_profiles VALUES(%s,1,%s,true,9999999999999)",
            (source_profile, Jsonb({})),
        )

    def request():
        rid, sid = uuid4(), uuid4()
        with database(url, schema=schema) as c:
            c.execute(
                "INSERT INTO requests(id,owner_id,current_version,created_at,updated_at) "
                "VALUES(%s,%s,1,1,1)",
                (rid, owner),
            )
            c.execute("INSERT INTO request_versions VALUES(%s,1,'{}','assertion',1)", (rid,))
            c.execute(
                "INSERT INTO supplier_sources VALUES(%s,%s,1,'Assertion',"
                "'https://vendor.example.com/offer',%s,1,'vendor.example.com')",
                (sid, rid, source_profile),
            )
        return rid, sid

    return url, schema, owner, other, request


def test_single_claim_idempotency_and_owner_boundary(queue):
    url, schema, owner, other, request = queue
    rid, _ = request()
    with database(url, schema=schema) as c:
        job = jobs.enqueue(c, owner, rid, 1, "claim_assertion")
        assert jobs.enqueue(c, owner, rid, 1, "claim_assertion")["id"] == job["id"]
    with pytest.raises(ApiError), database(url, schema=schema) as c:
        jobs.enqueue(c, owner, rid, 2, "claim_assertion")
    with pytest.raises(ApiError), database(url, schema=schema) as c:
        jobs.get(c, other, job["id"])

    def claim():
        with database(url, schema=schema) as c:
            return jobs.claim(c, uuid4())

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: claim(), range(3)))
    active = [r for r in results if r]
    assert len(active) == 1
    job = active[0]
    with database(url, schema=schema) as c:
        assert jobs.heartbeat(c, job["id"], job["fence"], job["lease_holder"])["state"] == "running"
        jobs.finish(c, job["id"], job["fence"], job["lease_holder"], success=False)


def test_expired_attempt_requires_cleanup_before_reclaim_and_fences_old_completion(queue):
    url, schema, owner, _, request = queue
    rid, source = request()
    with database(url, schema=schema) as c:
        jobs.enqueue(c, owner, rid, 1, "recovery_assertion")
        first = jobs.claim(c, uuid4())
        task = jobs.start_task(c, first["id"], first["fence"], first["lease_holder"], source)
        c.execute("UPDATE jobs SET lease_until=%s WHERE id=%s", (jobs.clock(c) - 1, first["id"]))
    for action in ("heartbeat", "finish"):
        with pytest.raises(jobs.FenceLost), database(url, schema=schema) as c:
            if action == "heartbeat":
                jobs.heartbeat(c, first["id"], first["fence"], first["lease_holder"])
            else:
                jobs.finish(c, first["id"], first["fence"], first["lease_holder"], success=True)
    with database(url, schema=schema) as c:
        assert jobs.expired(c)[0]["state"] == "recovering"
        assert jobs.claim(c, uuid4()) is None
    with pytest.raises(ValueError), database(url, schema=schema) as c:
        jobs.recover(c, first["id"], first["fence"], first["lease_holder"])
    with database(url, schema=schema) as c:
        jobs.task_cleaned(
            c, first["id"], first["fence"], first["lease_holder"], task["task_id"], "interrupted"
        )
        jobs.recover(c, first["id"], first["fence"], first["lease_holder"])
        second = jobs.claim(c, uuid4())
        assert second["attempt"] == 2 and second["fence"] != first["fence"]
    with pytest.raises(jobs.FenceLost), database(url, schema=schema) as c:
        jobs.task_cleaned(
            c,
            first["id"],
            first["fence"],
            first["lease_holder"],
            task["task_id"],
            "captured",
            "a" * 64,
        )
    with database(url, schema=schema) as c:
        jobs.cancel(c, owner, second["id"])
        assert (
            jobs.finish(c, second["id"], second["fence"], second["lease_holder"], success=True)[
                "state"
            ]
            == "cancelled"
        )


def test_cancel_and_complete_capture_require_exact_task_cleanup(queue):
    url, schema, owner, _, request = queue
    rid, source = request()
    with database(url, schema=schema) as c:
        job = jobs.enqueue(c, owner, rid, 1, "cancel_assertion")
        job = jobs.claim(c, uuid4())
        task = jobs.start_task(c, job["id"], job["fence"], job["lease_holder"], source)
        assert jobs.cancel(c, owner, job["id"])["state"] == "cancelling"
    with pytest.raises(ValueError), database(url, schema=schema) as c:
        jobs.finish(c, job["id"], job["fence"], job["lease_holder"], success=True)
    with database(url, schema=schema) as c:
        jobs.task_cleaned(
            c, job["id"], job["fence"], job["lease_holder"], task["task_id"], "cancelled"
        )
        assert (
            jobs.finish(c, job["id"], job["fence"], job["lease_holder"], success=True)["state"]
            == "cancelled"
        )
        events = c.execute(
            "SELECT * FROM events WHERE job_id=%s ORDER BY id", (job["id"],)
        ).fetchall()
        assert [e["kind"] for e in events] == [
            "job_queued",
            "job_started",
            "job_cancel_requested",
            "job_cancelled",
        ]
        assert all(
            set(e["safe_payload_json"]) == {"job_id", "version", "state", "attempt"} for e in events
        )
    rid, source = request()
    with database(url, schema=schema) as c:
        jobs.enqueue(c, owner, rid, 1, "complete_assertion")
        job = jobs.claim(c, uuid4())
    with pytest.raises(ValueError), database(url, schema=schema) as c:
        jobs.finish(c, job["id"], job["fence"], job["lease_holder"], success=True)
    with database(url, schema=schema) as c:
        task = jobs.start_task(c, job["id"], job["fence"], job["lease_holder"], source)
        jobs.task_cleaned(
            c, job["id"], job["fence"], job["lease_holder"], task["task_id"], "captured", "a" * 64
        )
        assert (
            jobs.finish(c, job["id"], job["fence"], job["lease_holder"], success=True)["state"]
            == "succeeded"
        )
