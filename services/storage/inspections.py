"""Operator readiness, bounded queue admission and durable inspection lookup."""

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from services.api.auth import iso_ms
from services.api.errors import ApiError
from services.common.source_policy import SourceProfile, profile_hash
from services.domain.contracts import JobView, content_hash
from services.domain.inspections import InspectionView
from services.storage import jobs
from services.storage.database import lock_owner
from services.storage.requests import owned

HEALTH_MS = 75000


def job_view(row):
    return JobView(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        request_version=row["request_version"],
        state=row["state"],
        attempt=row["attempt"],
        created_at=iso_ms(row["created_at"]),
        finished_at=iso_ms(row["finished_at"]) if row["finished_at"] else None,
        failure_code=row["failure_code"],
    )


def heartbeat(conn, holder, available, profiles):
    conn.execute(
        "INSERT INTO runner_health VALUES(1,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET "
        "holder=excluded.holder,checked_at=excluded.checked_at,available=excluded.available,"
        "profiles_json=excluded.profiles_json",
        (holder, jobs.clock(conn), available, Jsonb(profiles)),
    )


def health(conn, enabled):
    row = conn.execute("SELECT * FROM runner_health WHERE id=1").fetchone()
    now = jobs.clock(conn)
    if (
        not enabled
        or not row
        or not row["available"]
        or not 0 <= now - row["checked_at"] < HEALTH_MS
    ):
        return None
    return {(p["id"], p["version"]): p["hash"] for p in row["profiles_json"]}


def status(conn, owner_id, request_id, enabled):
    request = owned(conn, owner_id, request_id)
    version = request["current_version"]
    latest = conn.execute(
        "SELECT * FROM jobs WHERE request_id=%s AND owner_id=%s AND request_version=%s "
        "AND kind='inspect' ORDER BY created_at DESC,id DESC LIMIT 1",
        (request_id, owner_id, version),
    ).fetchone()
    profiles = health(conn, enabled)
    reason = None
    if request["archived_at"]:
        reason = "REQUEST_ARCHIVED"
    elif profiles is None:
        reason = "WORKER_UNAVAILABLE"
    elif conn.execute(
        "SELECT 1 FROM receipts WHERE request_id=%s AND request_version=%s", (request_id, version)
    ).fetchone():
        reason = "ALREADY_RELEASED"
    else:
        sources = conn.execute(
            "SELECT s.*,p.profile_json,p.active,p.expires_at FROM supplier_sources s "
            "JOIN source_profiles p ON p.id=s.profile_id AND p.version=s.profile_version "
            "WHERE s.request_id=%s AND s.version=%s FOR SHARE OF p",
            (request_id, version),
        ).fetchall()
        if not sources:
            reason = "SOURCE_REQUIRED"
        for source in sources:
            try:
                profile = SourceProfile.model_validate(source["profile_json"])
                profile.admit(source["canonical_public_url"], datetime.now(UTC))
                if (
                    not source["active"]
                    or source["expires_at"] <= jobs.clock(conn)
                    or profiles.get((profile.id, profile.version)) != profile_hash(profile)
                ):
                    reason = "SOURCE_PROFILE_UNAVAILABLE"
            except ValueError:
                reason = "SOURCE_PROFILE_UNAVAILABLE"
    return InspectionView(
        request_version=version,
        enabled=reason is None,
        reason=reason,
        job=job_view(latest) if latest else None,
    )


def begin(conn, owner_id, request_id, body, key, enabled):
    lock_owner(conn, str(owner_id))
    owned(conn, owner_id, request_id, lock=True)
    if body.public_scope_seen is not True:
        raise ApiError(422, "PUBLIC_SCOPE_ACKNOWLEDGEMENT_REQUIRED", "inspection.ackRequired")
    prior = conn.execute(
        "SELECT * FROM jobs WHERE owner_id=%s AND request_id=%s AND kind='inspect' "
        "AND idempotency_key=%s",
        (owner_id, request_id, key),
    ).fetchone()
    if prior:
        if prior["request_version"] != body.current_version:
            raise ApiError(409, "IDEMPOTENCY_MISMATCH", "error.idempotency")
        return job_view(prior)
    view = status(conn, owner_id, request_id, enabled)
    if view.request_version != body.current_version:
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    if not view.enabled:
        raise ApiError(
            503 if view.reason == "WORKER_UNAVAILABLE" else 422,
            view.reason,
            "error.worker" if view.reason == "WORKER_UNAVAILABLE" else "inspection.sourceRequired",
        )
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('latch-inspection-admission'))")
    counts = conn.execute(
        "SELECT count(*) AS total,count(*) FILTER(WHERE owner_id=%s) AS owned FROM jobs "
        "WHERE state IN ('queued','running','recovering','cancelling')",
        (owner_id,),
    ).fetchone()
    if counts["total"] >= 16 or counts["owned"] >= 2:
        raise ApiError(429, "QUEUE_LIMIT", "inspection.queueFull")
    return job_view(jobs.enqueue(conn, owner_id, request_id, body.current_version, key))


def save_plan(conn, job, holder, plan, usage):
    live = jobs.leased(conn, job["id"], job["fence"], holder)
    if live["cancel_requested_at"]:
        raise jobs.FenceLost("JOB_CANCELLED")
    body = plan.model_dump(mode="json")
    conn.execute(
        "INSERT INTO inspection_plans VALUES(%s,%s,%s,%s,%s,%s)",
        (job["id"], job["fence"], Jsonb(body), content_hash(body), Jsonb(usage), jobs.clock(conn)),
    )
    jobs.event(conn, live, "inspection_planned")
