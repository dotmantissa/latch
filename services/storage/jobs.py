"""Durable Postgres queue. Every worker completion is fenced and cleanup-confirmed."""

from uuid import uuid4

from psycopg.types.json import Jsonb

from services.api.errors import ApiError
from services.domain.contracts import content_hash
from services.storage.requests import owned

LEASE_MS = 30_000
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


class FenceLost(RuntimeError):
    pass


def clock(conn) -> int:
    return conn.execute(
        "SELECT floor(extract(epoch FROM clock_timestamp())*1000)::bigint AS at"
    ).fetchone()["at"]


def event(conn, job, kind: str) -> None:
    # Fixed server-authored fields only: no source, user text, provider answers or credentials.
    conn.execute(
        "INSERT INTO events(owner_id,request_id,kind,safe_payload_json,at,job_id) "
        "VALUES(%s,%s,%s,%s,%s,%s)",
        (
            job["owner_id"],
            job["request_id"],
            kind,
            Jsonb(
                {
                    "job_id": str(job["id"]),
                    "version": job["request_version"],
                    "state": job["state"],
                    "attempt": job["attempt"],
                }
            ),
            clock(conn),
            job["id"],
        ),
    )


def get(conn, owner_id, job_id, *, lock=False):
    row = conn.execute(
        "SELECT * FROM jobs WHERE id=%s AND owner_id=%s" + (" FOR UPDATE" if lock else ""),
        (job_id, owner_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    return row


def enqueue(conn, owner_id, request_id, version: int, key: str, *, kind="inspect"):
    request = owned(conn, owner_id, request_id, lock=True)
    intent = content_hash({"request_id": str(request_id), "version": version, "kind": kind})
    previous = conn.execute(
        "SELECT * FROM jobs WHERE owner_id=%s AND request_id=%s AND kind=%s AND idempotency_key=%s",
        (owner_id, request_id, kind, key),
    ).fetchone()
    if previous:
        if previous["intent_hash"] != intent:
            raise ApiError(409, "IDEMPOTENCY_MISMATCH", "error.idempotency")
        return previous
    if request["current_version"] != version or request["archived_at"]:
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    if conn.execute(
        "SELECT 1 FROM jobs WHERE request_id=%s AND state IN "
        "('queued','running','recovering','cancelling')",
        (request_id,),
    ).fetchone():
        raise ApiError(409, "JOB_ALREADY_ACTIVE", "error.conflict")
    at = clock(conn)
    row = conn.execute(
        "INSERT INTO jobs(id,owner_id,request_id,request_version,kind,state,idempotency_key,"
        "intent_hash,created_at,deadline_at) VALUES(%s,%s,%s,%s,%s,'queued',%s,%s,%s,%s) "
        "RETURNING *",
        (uuid4(), owner_id, request_id, version, kind, key, intent, at, at + 180_000),
    ).fetchone()
    event(conn, row, "job_queued")
    return row


def claim(conn, holder):
    # Global single job, also serializes recovery with concurrent runner processes.
    conn.execute("SELECT id FROM runner_slot WHERE id=1 FOR UPDATE")
    if conn.execute(
        "SELECT 1 FROM jobs WHERE state IN ('running','recovering','cancelling') LIMIT 1"
    ).fetchone():
        return None
    row = conn.execute(
        "SELECT * FROM jobs WHERE state='queued' ORDER BY created_at,id "
        "LIMIT 1 FOR UPDATE SKIP LOCKED"
    ).fetchone()
    if row is None:
        return None
    at = clock(conn)
    request = owned(conn, row["owner_id"], row["request_id"])
    if (
        at >= row["deadline_at"]
        or row["attempt"] >= 2
        or request["archived_at"]
        or (request["current_version"] != row["request_version"])
    ):
        end(conn, row, "failed", "JOB_NO_LONGER_RUNNABLE")
        return None
    fence = uuid4()
    row = conn.execute(
        "UPDATE jobs SET state='running',attempt=attempt+1,fence=%s,lease_holder=%s,"
        "lease_until=%s,heartbeat_at=%s WHERE id=%s RETURNING *",
        (fence, holder, min(at + LEASE_MS, row["deadline_at"]), at, row["id"]),
    ).fetchone()
    conn.execute(
        "INSERT INTO job_attempts VALUES(%s,%s,%s,%s,%s)",
        (row["id"], row["attempt"], fence, holder, at),
    )
    event(conn, row, "job_started")
    return row


def leased(conn, job_id, fence, holder, *, cleanup=False):
    row = conn.execute("SELECT * FROM jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
    at = clock(conn)
    if row is None or row["fence"] != fence or row["lease_holder"] != holder:
        raise FenceLost("JOB_FENCE_LOST")
    if cleanup and row["state"] == "recovering":
        return row
    if (
        row["state"] not in ("running", "cancelling")
        or at >= row["lease_until"]
        or at < row["heartbeat_at"]
    ):
        raise FenceLost("JOB_LEASE_EXPIRED")
    return row


def heartbeat(conn, job_id, fence, holder):
    row = leased(conn, job_id, fence, holder)
    at = clock(conn)
    if at >= row["deadline_at"]:
        raise FenceLost("JOB_DEADLINE_EXPIRED")
    return conn.execute(
        "UPDATE jobs SET heartbeat_at=%s,lease_until=%s WHERE id=%s RETURNING *",
        (at, min(at + LEASE_MS, row["deadline_at"]), job_id),
    ).fetchone()


def end(conn, row, state: str, failure: str | None = None):
    row = conn.execute(
        "UPDATE jobs SET state=%s,finished_at=%s,failure_code=%s,lease_until=NULL "
        "WHERE id=%s RETURNING *",
        (state, clock(conn), failure, row["id"]),
    ).fetchone()
    event(conn, row, "job_" + state)
    return row


def cancel(conn, owner_id, job_id):
    row = get(conn, owner_id, job_id, lock=True)
    if row["state"] in TERMINAL:
        return row
    row = conn.execute(
        "UPDATE jobs SET cancel_requested_at=COALESCE(cancel_requested_at,%s),"
        "state=CASE WHEN state='queued' THEN 'queued' ELSE 'cancelling' END "
        "WHERE id=%s RETURNING *",
        (clock(conn), job_id),
    ).fetchone()
    if row["state"] == "queued":
        return end(conn, row, "cancelled")
    event(conn, row, "job_cancel_requested")
    return row


def start_task(conn, job_id, fence, holder, source_id):
    row = leased(conn, job_id, fence, holder)
    if row["state"] != "running" or row["cancel_requested_at"]:
        raise FenceLost("JOB_CANCELLED")
    if not conn.execute(
        "SELECT 1 FROM supplier_sources WHERE id=%s AND request_id=%s AND version=%s",
        (source_id, row["request_id"], row["request_version"]),
    ).fetchone():
        raise ValueError("TASK_SOURCE_MISMATCH")
    previous = conn.execute(
        "SELECT * FROM job_tasks WHERE job_id=%s AND fence=%s AND source_id=%s",
        (job_id, fence, source_id),
    ).fetchone()
    if previous:
        return previous
    return conn.execute(
        "INSERT INTO job_tasks(task_id,job_id,fence,source_id,started_at) "
        "VALUES(%s,%s,%s,%s,%s) RETURNING *",
        (uuid4(), job_id, fence, source_id, clock(conn)),
    ).fetchone()


def task_cleaned(conn, job_id, fence, holder, task_id, outcome: str, artifact_hash=None):
    leased(conn, job_id, fence, holder, cleanup=True)
    row = conn.execute(
        "UPDATE job_tasks SET cleanup_at=%s,outcome=%s,artifact_hash=%s "
        "WHERE task_id=%s AND job_id=%s AND fence=%s AND cleanup_at IS NULL RETURNING *",
        (clock(conn), outcome, artifact_hash, task_id, job_id, fence),
    ).fetchone()
    if row is None:
        raise FenceLost("TASK_ALREADY_CLEANED_OR_UNKNOWN")
    return row


def all_clean(conn, row) -> bool:
    return not conn.execute(
        "SELECT 1 FROM job_tasks WHERE job_id=%s AND cleanup_at IS NULL", (row["id"],)
    ).fetchone()


def finish(conn, job_id, fence, holder, *, success: bool):
    row = leased(conn, job_id, fence, holder)
    if not all_clean(conn, row):
        raise ValueError("CLEANUP_NOT_CONFIRMED")
    if row["cancel_requested_at"]:
        return end(conn, row, "cancelled")
    request = owned(conn, row["owner_id"], row["request_id"], lock=True)
    if request["current_version"] != row["request_version"] or request["archived_at"]:
        return end(conn, row, "failed", "REQUEST_VERSION_CHANGED")
    if success:
        counts = conn.execute(
            "SELECT count(*) AS n FROM job_tasks WHERE job_id=%s AND fence=%s "
            "AND outcome='captured' AND artifact_hash IS NOT NULL",
            (job_id, fence),
        ).fetchone()["n"]
        expected = conn.execute(
            "SELECT count(*) AS n FROM supplier_sources WHERE request_id=%s AND version=%s",
            (row["request_id"], row["request_version"]),
        ).fetchone()["n"]
        if not expected or counts != expected:
            raise ValueError("COMPLETE_CAPTURE_SET_REQUIRED")
    return end(conn, row, "succeeded" if success else "failed", None if success else "TASK_FAILED")


def expired(conn):
    conn.execute("SELECT id FROM runner_slot WHERE id=1 FOR UPDATE")
    rows = conn.execute(
        "SELECT * FROM jobs WHERE state IN ('running','cancelling','recovering') "
        "AND (lease_until<=%s OR deadline_at<=%s) FOR UPDATE",
        (clock(conn), clock(conn)),
    ).fetchall()
    result = []
    for row in rows:
        if row["state"] != "recovering":
            row = conn.execute(
                "UPDATE jobs SET state='recovering' WHERE id=%s RETURNING *", (row["id"],)
            ).fetchone()
            event(conn, row, "job_recovering")
        result.append(row)
    return result


def recover(conn, job_id, fence, holder):
    row = leased(conn, job_id, fence, holder, cleanup=True)
    if row["state"] != "recovering" or not all_clean(conn, row):
        raise ValueError("RECOVERY_CLEANUP_NOT_CONFIRMED")
    if row["cancel_requested_at"]:
        return end(conn, row, "cancelled")
    if row["attempt"] >= 2 or clock(conn) >= row["deadline_at"]:
        return end(conn, row, "failed", "RECOVERY_BUDGET_EXHAUSTED")
    row = conn.execute(
        "UPDATE jobs SET state='queued',lease_until=NULL,lease_holder=NULL,fence=NULL "
        "WHERE id=%s RETURNING *",
        (job_id,),
    ).fetchone()
    event(conn, row, "job_requeued")
    return row
