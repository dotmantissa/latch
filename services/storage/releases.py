"""All-source recheck and one atomic idempotent internal receipt, without network calls."""

from uuid import uuid4

from psycopg.types.json import Jsonb

from services.api.auth import ABSOLUTE_MS, IDLE_MS, iso_ms
from services.api.errors import ApiError
from services.domain.contracts import content_hash
from services.domain.releases import ReceiptView, ReleaseAttemptView, source_diff
from services.storage import decisions, jobs
from services.storage.requests import owned


def view(conn, owner_id, attempt_id):
    row = conn.execute(
        "SELECT a.*,j.state AS job_state,o.state AS outcome,o.reason,o.diff_json,"
        "r.id AS receipt_id "
        "FROM release_attempts a JOIN jobs j ON j.id=a.job_id "
        "LEFT JOIN release_outcomes o ON o.attempt_id=a.id "
        "LEFT JOIN receipts r ON r.attempt_id=a.id "
        "WHERE a.id=%s AND a.owner_id=%s",
        (attempt_id, owner_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    state = row["outcome"] or (
        "queued"
        if row["job_state"] == "queued"
        else "blocked"
        if row["job_state"] in ("failed", "cancelled")
        else "running"
    )
    return ReleaseAttemptView(
        id=row["id"],
        request_id=row["request_id"],
        request_version=row["request_version"],
        approval_id=row["approval_id"],
        job_id=row["job_id"],
        state=state,
        reason=row["reason"] or ("RECHECK_FAILED" if state == "blocked" else None),
        differences=row["diff_json"] or [],
        receipt_id=row["receipt_id"],
        created_at=iso_ms(row["created_at"]),
    )


def begin(conn, owner_id, request_id, session, body, key):
    owned(conn, owner_id, request_id, lock=True)
    intent = content_hash(body.model_dump(mode="json"))
    prior = conn.execute(
        "SELECT id,intent_hash FROM release_attempts WHERE owner_id=%s AND request_id=%s "
        "AND idempotency_key=%s",
        (owner_id, request_id, key),
    ).fetchone()
    if prior:
        if prior["intent_hash"] != intent:
            raise ApiError(409, "IDEMPOTENCY_MISMATCH", "error.idempotency")
        return view(conn, owner_id, prior["id"])
    approval = conn.execute(
        "SELECT * FROM approvals WHERE id=%s AND owner_id=%s AND request_id=%s",
        (body.approval_id, owner_id, request_id),
    ).fetchone()
    if approval is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    if (approval["packet_hash"], approval["request_version"], approval["session_id"]) != (
        body.approval_hash,
        body.request_version,
        session["id"],
    ) or decisions.approval_state(conn, approval) != "active":
        raise ApiError(412, "APPROVAL_INVALID", "error.conflict")
    if body.scope_seen is not True:
        raise ApiError(422, "SCOPE_ACKNOWLEDGEMENT_REQUIRED")
    if conn.execute(
        "SELECT 1 FROM receipts WHERE request_id=%s AND request_version=%s",
        (request_id, body.request_version),
    ).fetchone():
        raise ApiError(409, "ALREADY_RELEASED")
    job = jobs.enqueue(conn, owner_id, request_id, body.request_version, key, kind="recheck")
    row = conn.execute(
        "INSERT INTO release_attempts VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (
            uuid4(),
            owner_id,
            request_id,
            body.request_version,
            approval["id"],
            session["id"],
            job["id"],
            key,
            intent,
            jobs.clock(conn),
        ),
    ).fetchone()
    return view(conn, owner_id, row["id"])


def cancel(conn, owner_id, attempt_id):
    attempt = conn.execute(
        "SELECT * FROM release_attempts WHERE id=%s AND owner_id=%s", (attempt_id, owner_id)
    ).fetchone()
    if attempt is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    owned(conn, owner_id, attempt["request_id"], lock=True)
    conn.execute("SELECT id FROM release_attempts WHERE id=%s FOR UPDATE", (attempt_id,))
    if not conn.execute(
        "SELECT 1 FROM release_outcomes WHERE attempt_id=%s", (attempt_id,)
    ).fetchone():
        jobs.cancel(conn, owner_id, attempt["job_id"])
        block(conn, attempt, "RELEASE_CANCELLED")
    return view(conn, owner_id, attempt_id)


def pages(conn, capture_id):
    return conn.execute(
        "SELECT * FROM captured_pages WHERE capture_id=%s ORDER BY page_index",
        (capture_id,),
    ).fetchall()


def block(conn, attempt, reason, differences=(), *, changed=False):
    conn.execute(
        "INSERT INTO release_outcomes VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (
            attempt["id"],
            "changed" if changed else "blocked",
            reason,
            Jsonb([d.model_dump(mode="json") for d in differences]),
            jobs.clock(conn),
        ),
    )
    if changed:
        conn.execute(
            "INSERT INTO approval_revocations VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            (attempt["approval_id"], attempt["owner_id"], jobs.clock(conn)),
        )


def finalize(conn, attempt_id):
    # Consistent lock order with API commands: identity, request, attempt, completed job, profiles.
    attempt = conn.execute("SELECT * FROM release_attempts WHERE id=%s", (attempt_id,)).fetchone()
    if attempt is None:
        return
    session = conn.execute(
        "SELECT s.*,u.active FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.id=%s FOR UPDATE OF s,u",
        (attempt["session_id"],),
    ).fetchone()
    owned(conn, attempt["owner_id"], attempt["request_id"], lock=True)
    conn.execute("SELECT id FROM release_attempts WHERE id=%s FOR UPDATE", (attempt_id,))
    if conn.execute("SELECT 1 FROM release_outcomes WHERE attempt_id=%s", (attempt_id,)).fetchone():
        return
    job = jobs.get(conn, attempt["owner_id"], attempt["job_id"], lock=True)
    if job["state"] not in jobs.TERMINAL:
        return
    if job["state"] != "succeeded" or job["kind"] != "recheck" or job["cancel_requested_at"]:
        block(conn, attempt, "RECHECK_FAILED")
        return
    at = jobs.clock(conn)
    if (
        session is None
        or session["user_id"] != attempt["owner_id"]
        or not session["active"]
        or session["revoked_at"] is not None
        or at >= session["absolute_expires_at"]
        or not 0 <= at - session["last_seen_at"] < IDLE_MS
        or not 0 <= at - session["created_at"] < ABSOLUTE_MS
    ):
        block(conn, attempt, "SESSION_EXPIRED")
        return
    approval = conn.execute(
        "SELECT * FROM approvals WHERE id=%s", (attempt["approval_id"],)
    ).fetchone()
    if decisions.approval_state(conn, approval) != "active" or approval[
        "packet_hash"
    ] != content_hash(approval["packet_json"]):
        block(conn, attempt, "APPROVAL_INVALID")
        return
    fresh = conn.execute(
        "SELECT * FROM source_captures WHERE job_id=%s AND fence=%s ORDER BY source_id",
        (job["id"], job["fence"]),
    ).fetchall()
    approved = approval["packet_json"]["comparison"]["sources"]
    if len(fresh) != len(approved) or {str(c["source_id"]) for c in fresh} != {
        s["source_id"] for s in approved
    }:
        block(conn, attempt, "COMPLETE_SOURCE_SET_REQUIRED")
        return
    diffs, manifest, completed, started = [], [], [], []
    for source in approved:
        old = conn.execute(
            "SELECT * FROM source_captures WHERE id=%s", (source["capture_id"],)
        ).fetchone()
        new = next(c for c in fresh if str(c["source_id"]) == source["source_id"])
        a, b = pages(conn, old["id"]), pages(conn, new["id"])
        completed.extend(p["completed_at"] for p in b)
        started.extend(p["started_at"] for p in b)
        if (
            new["request_version"] != attempt["request_version"]
            or (new["profile_id"], new["profile_version"])
            != (old["profile_id"], old["profile_version"])
            or len(a) != len(b)
            or [p["source_url"] for p in a] != [p["source_url"] for p in b]
        ):
            block(conn, attempt, "SOURCE_SCOPE_CHANGED")
            return
        diff = source_diff(old, new, a, b)
        diffs.append(diff)
        manifest.append(
            {
                "source_id": str(new["source_id"]),
                "capture_id": str(new["id"]),
                "capture_hash": new["capture_hash"],
                "fingerprint": new["content_fingerprint"],
                "profile_id": new["profile_id"],
                "profile_version": new["profile_version"],
                "pages": [
                    {
                        "artifact_id": str(p["id"]),
                        "source_url": p["source_url"],
                        "started_at": iso_ms(p["started_at"]),
                        "completed_at": iso_ms(p["completed_at"]),
                        "raster_hash": p["sanitized_png_hash"],
                        "text_hash": p["text_hash"],
                    }
                    for p in b
                ],
            }
        )
    if any(d.text_changed or d.raster_changed for d in diffs):
        block(conn, attempt, "SOURCE_CONTENT_CHANGED", diffs, changed=True)
        return
    snapshot = conn.execute(
        "SELECT snapshot_json FROM request_versions WHERE request_id=%s AND version=%s",
        (attempt["request_id"], attempt["request_version"]),
    ).fetchone()["snapshot_json"]
    profile_expiry = conn.execute(
        "SELECT min(p.expires_at) AS expires FROM source_profiles p "
        "JOIN supplier_sources s ON s.profile_id=p.id AND s.profile_version=p.version "
        "WHERE s.request_id=%s AND s.version=%s",
        (attempt["request_id"], attempt["request_version"]),
    ).fetchone()["expires"]
    # Last wall-clock check after every immutable read, immediately before receipt insertion.
    at = jobs.clock(conn)
    for capture in fresh:
        for p in pages(conn, capture["id"]):
            if not job["created_at"] <= p["started_at"] <= p["completed_at"] <= at:
                block(conn, attempt, "CAPTURE_CLOCK_INVALID")
                return
            if at - p["completed_at"] > 60000:
                block(conn, attempt, "SOURCE_RECHECK_STALE")
                return
    # Retain transaction locks and check expiry again after all source reads.
    at = jobs.clock(conn)
    if (
        at >= approval["expires_at"]
        or at >= session["absolute_expires_at"]
        or at - session["last_seen_at"] >= IDLE_MS
        or at >= profile_expiry
        or not completed
        or at - min(completed) > 60000
        or max(completed) > at
        or min(started) < job["created_at"]
    ):
        block(conn, attempt, "APPROVAL_EXPIRED")
        return
    if conn.execute(
        "SELECT 1 FROM receipts WHERE request_id=%s AND request_version=%s",
        (attempt["request_id"], attempt["request_version"]),
    ).fetchone():
        block(conn, attempt, "ALREADY_RELEASED")
        return
    receipt_id = uuid4()
    record = {
        "receipt_schema": "internal-release-v1",
        "id": str(receipt_id),
        "request_id": str(attempt["request_id"]),
        "request_version": attempt["request_version"],
        "worksheet": snapshot,
        "approval_id": str(approval["id"]),
        "approval_hash": approval["packet_hash"],
        "approved_packet": approval["packet_json"],
        "fresh_sources": manifest,
        "committed_at": iso_ms(at),
        "scope": decisions.SCOPE,
    }
    conn.execute(
        "INSERT INTO receipts VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            receipt_id,
            attempt_id,
            attempt["request_id"],
            attempt["request_version"],
            attempt["owner_id"],
            approval["id"],
            Jsonb(record),
            content_hash(record),
            at,
        ),
    )
    conn.execute(
        "INSERT INTO release_outcomes VALUES(%s,'released',NULL,%s,%s)",
        (attempt_id, Jsonb([d.model_dump(mode="json") for d in diffs]), at),
    )
    jobs.event(conn, job, "internal_release_committed")


def reconcile(conn):
    return [
        r["id"]
        for r in conn.execute(
            "SELECT a.id FROM release_attempts a JOIN jobs j ON j.id=a.job_id "
            "LEFT JOIN release_outcomes o ON o.attempt_id=a.id "
            "WHERE o.attempt_id IS NULL AND j.state IN ('succeeded','failed','cancelled') "
            "ORDER BY a.created_at LIMIT 10",
        ).fetchall()
    ]


def receipt(conn, owner_id, receipt_id):
    row = conn.execute(
        "SELECT * FROM receipts WHERE id=%s AND owner_id=%s", (receipt_id, owner_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    if content_hash(row["record_json"]) != row["record_hash"]:
        raise ApiError(503, "RECEIPT_HASH_MISMATCH")
    return ReceiptView(
        id=row["id"],
        request_id=row["request_id"],
        request_version=row["request_version"],
        committed_at=iso_ms(row["committed_at"]),
        record_hash=row["record_hash"],
        record=row["record_json"],
    )
