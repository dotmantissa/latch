"""Immutable comparisons, explicit feasible-only selection and expiring approval."""

from datetime import UTC, datetime
from uuid import uuid4

from psycopg.types.json import Jsonb

from services.api.auth import IDLE_MS, REAUTH_MS, iso_ms, user_view
from services.api.errors import ApiError
from services.domain.contracts import UserView, content_hash
from services.domain.correspondence import Correspondence
from services.domain.correspondence import blockers as image_blockers
from services.domain.decisions import (
    ApprovalView,
    ComparedSource,
    ComparisonView,
    DecisionView,
    SelectionView,
)
from services.domain.extraction import Extraction
from services.domain.reviews import Decision, reviewed_offer
from services.domain.rules import POLICY_VERSION, calculate_basket
from services.storage import jobs
from services.storage.requests import owned
from services.storage.reviews import FieldView, ReviewView

SCOPE = "Internal decision record only. No order, payment, reservation or price lock."


def latest(conn, table, request_id):
    # Table names are private constants, never request/model content.
    if table not in ("comparisons", "selections", "approvals"):
        raise ValueError("Unsupported decision table")
    order = {"comparisons": "evaluated_at", "selections": "revision", "approvals": "generation"}
    return conn.execute(
        f"SELECT * FROM {table} WHERE request_id=%s ORDER BY {order[table]} DESC,id DESC LIMIT 1",
        (request_id,),
    ).fetchone()


def derive(conn, owner_id, request_id, *, ignore_job=None):
    request = owned(conn, owner_id, request_id, lock=True)
    version = request["current_version"]
    snapshot = conn.execute(
        "SELECT content_hash,snapshot_json FROM request_versions "
        "WHERE request_id=%s AND version=%s",
        (request_id, version),
    ).fetchone()
    sources = conn.execute(
        "SELECT s.*,c.id AS capture_id,c.capture_hash,c.content_fingerprint,"
        "e.id AS extraction_id,e.proposal_json,e.proposal_hash,h.version AS review_version,"
        "i.result_json,p.active,p.expires_at FROM supplier_sources s "
        "JOIN source_profiles p ON p.id=s.profile_id AND p.version=s.profile_version "
        "LEFT JOIN source_captures c ON c.source_id=s.id AND c.job_id=("
        "SELECT id FROM jobs WHERE request_id=%s AND request_version=%s AND owner_id=%s "
        "AND kind='inspect' AND state='succeeded' ORDER BY finished_at DESC,id DESC LIMIT 1) "
        "AND c.fence=(SELECT fence FROM jobs WHERE id=c.job_id) "
        "LEFT JOIN source_extractions e ON e.capture_id=c.id "
        "LEFT JOIN review_heads h ON h.extraction_id=e.id "
        "LEFT JOIN source_correspondence i ON i.capture_id=c.id "
        "WHERE s.request_id=%s AND s.version=%s ORDER BY s.id FOR SHARE OF p",
        (request_id, version, owner_id, request_id, version),
    ).fetchall()
    ids = [s["extraction_id"] for s in sources if s["extraction_id"]]
    rows = (
        conn.execute(
            "SELECT DISTINCT ON (r.extraction_id,r.decision_json->>'item_key',"
            "r.decision_json->>'kind') "
            "r.*,u.username,u.display_name FROM field_reviews r JOIN users u ON u.id=r.reviewer_id "
            "WHERE r.extraction_id=ANY(%s) ORDER BY r.extraction_id,r.decision_json->>'item_key',"
            "r.decision_json->>'kind',r.version DESC",
            (ids,),
        ).fetchall()
        if ids
        else []
    )
    active = conn.execute(
        "SELECT id FROM jobs WHERE request_id=%s AND state IN "
        "('queued','running','recovering','cancelling')",
        (request_id,),
    ).fetchall()
    at = jobs.clock(conn)
    global_blockers = []
    if request["archived_at"]:
        global_blockers.append("REQUEST_ARCHIVED")
    if not sources or any(not s["capture_id"] for s in sources):
        global_blockers.append("COMPLETE_SOURCE_SET_REQUIRED")
    if any(j["id"] != ignore_job for j in active):
        global_blockers.append("INSPECTION_ACTIVE")
    result, attribution = [], []
    for source in sources:
        if source["extraction_id"] is None:
            continue
        extraction = Extraction.model_validate(source["proposal_json"])
        latest_reviews = [
            ReviewView(
                id=r["id"],
                version=r["version"],
                reviewer=UserView(
                    id=str(r["reviewer_id"]),
                    username=r["username"],
                    display_name=r["display_name"],
                ),
                created_at=iso_ms(r["created_at"]),
                decision=Decision.model_validate(r["decision_json"]),
            )
            for r in rows
            if r["extraction_id"] == source["extraction_id"]
        ]
        by_key = {(r.decision.item_key, r.decision.kind): r for r in latest_reviews}
        fields = []
        for field in extraction.fields:
            review = by_key.get((field.item_key, field.kind))
            fields.append(
                FieldView(
                    original=field,
                    latest_review=review,
                    state=review.decision.state
                    if review
                    else {
                        "supported": "extracted",
                        "ambiguous": "disputed",
                        "unknown": "unknown",
                    }[field.state],
                    value=review.decision.value if review else field.value,
                )
            )
        value = snapshot["snapshot_json"]
        if not {"items", "budget_cents", "required_by"} <= set(value):
            global_blockers.append("WORKSHEET_REQUIRED")
            continue
        basket = calculate_basket(
            {i["key"]: i["required_units"] for i in value["items"]},
            reviewed_offer(extraction, [r.decision for r in latest_reviews]),
            value["budget_cents"],
            datetime.fromisoformat(value["required_by"]),
            datetime.fromtimestamp(at / 1000, UTC),
        )
        image = (
            Correspondence.model_validate(source["result_json"]) if source["result_json"] else None
        )
        blockers = image_blockers(image)
        if not source["active"] or source["expires_at"] <= at:
            blockers.append("SOURCE_PROFILE_EXPIRED")
            global_blockers.append("SOURCE_PROFILE_EXPIRED")
        entry = ComparedSource(
            source_id=source["id"],
            label=source["label"],
            capture_id=source["capture_id"],
            extraction_id=source["extraction_id"],
            capture_hash=source["capture_hash"],
            content_fingerprint=source["content_fingerprint"],
            proposal_hash=source["proposal_hash"],
            review_version=source["review_version"] or 0,
            review_set_hash=content_hash(
                {
                    "proposal_hash": extraction.proposal_hash,
                    "review_ids": sorted(str(r.id) for r in latest_reviews),
                }
            ),
            correspondence_hash=image.result_hash if image else None,
            reviewed_fields=[f.model_dump(mode="json") for f in fields],
            profile_id=source["profile_id"],
            profile_version=source["profile_version"],
            basket=basket,
            blockers=blockers,
            selectable=basket.feasible and not blockers,
        )
        result.append(entry)
        attribution.append(
            entry.model_dump(mode="json", exclude={"basket", "blockers", "selectable", "rank"})
        )
    ranked = sorted(
        [s for s in result if s.selectable],
        key=lambda s: (
            s.basket.complete_total_cents,
            datetime.fromisoformat(
                next(
                    f["value"]
                    for f in s.reviewed_fields
                    if f["original"]["kind"] == "latest_arrival"
                )
            ),
            str(s.source_id),
        ),
    )
    ranks = {s.source_id: i + 1 for i, s in enumerate(ranked)}
    result = [s.model_copy(update={"rank": ranks.get(s.source_id)}) for s in result]
    signature = {
        "decision_schema": "comparison-v1",
        "policy_version": POLICY_VERSION,
        "request_id": str(request_id),
        "request_version": version,
        "request_hash": snapshot["content_hash"],
        "sources": attribution,
    }
    if len(result) != len(sources):
        global_blockers.append("COMPLETE_EXTRACTION_SET_REQUIRED")
    return signature, result, sorted(set(global_blockers))


def comparison_view(conn, owner_id, row, *, ignore_job=None):
    signature, current_sources, blockers = derive(
        conn, owner_id, row["request_id"], ignore_job=ignore_job
    )
    current = content_hash(signature) == row["packet_hash"] and not blockers
    return ComparisonView(
        id=row["id"],
        request_version=row["request_version"],
        packet_hash=row["packet_hash"],
        evaluated_at=iso_ms(row["evaluated_at"]),
        current=current,
        blockers=blockers if current else sorted(set(blockers + ["COMPARISON_CHANGED"])),
        sources=current_sources
        if current
        else [ComparedSource.model_validate(s) for s in row["packet_json"]["sources"]],
    )


def compare(conn, owner_id, request_id, version):
    request = owned(conn, owner_id, request_id, lock=True)
    if version != request["current_version"]:
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    signature, sources, blockers = derive(conn, owner_id, request_id)
    if blockers:
        raise ApiError(409, blockers[0], "error.conflict")
    digest = content_hash(signature)
    row = conn.execute(
        "SELECT * FROM comparisons WHERE request_id=%s AND packet_hash=%s",
        (request_id, digest),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "INSERT INTO comparisons VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                owner_id,
                request_id,
                version,
                digest,
                Jsonb(
                    {
                        "signature": signature,
                        "sources": [s.model_dump(mode="json") for s in sources],
                    }
                ),
                jobs.clock(conn),
            ),
        ).fetchone()
    return comparison_view(conn, owner_id, row)


def selection_view(row, current):
    return SelectionView(
        id=row["id"],
        source_id=row["source_id"],
        comparison_id=row["comparison_id"],
        revision=row["revision"],
        current=current,
        created_at=iso_ms(row["created_at"]),
    )


def choose(conn, owner_id, request_id, body, key):
    owned(conn, owner_id, request_id, lock=True)
    intent = content_hash(body.model_dump(mode="json"))
    prior = conn.execute(
        "SELECT * FROM selections WHERE owner_id=%s AND request_id=%s AND idempotency_key=%s",
        (owner_id, request_id, key),
    ).fetchone()
    if prior:
        if prior["intent_hash"] != intent:
            raise ApiError(409, "IDEMPOTENCY_MISMATCH", "error.idempotency")
        current = state(conn, owner_id, request_id).selection
        return selection_view(
            prior, bool(current and current.current and current.id == prior["id"])
        )
    comparison = conn.execute(
        "SELECT * FROM comparisons WHERE id=%s AND request_id=%s AND owner_id=%s",
        (body.comparison_id, request_id, owner_id),
    ).fetchone()
    if comparison is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    view = comparison_view(conn, owner_id, comparison)
    if not view.current or (view.request_version, view.packet_hash) != (
        body.request_version,
        body.comparison_hash,
    ):
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    selected = next((s for s in view.sources if s.source_id == body.source_id), None)
    if selected is None or not selected.selectable:
        raise ApiError(422, "OFFER_NOT_FEASIBLE")
    head = latest(conn, "selections", request_id)
    revision = head["revision"] if head else 0
    if revision >= 1000:
        raise ApiError(429, "SELECTION_LIMIT")
    if body.expected_revision != revision:
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    if conn.execute(
        "SELECT 1 FROM receipts WHERE request_id=%s AND request_version=%s",
        (request_id, body.request_version),
    ).fetchone():
        raise ApiError(409, "ALREADY_RELEASED")
    row = conn.execute(
        "INSERT INTO selections VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            uuid4(),
            request_id,
            body.request_version,
            body.comparison_id,
            body.source_id,
            revision + 1,
            owner_id,
            key,
            intent,
            jobs.clock(conn),
        ),
    ).fetchone()
    return selection_view(row, True)


def selected_current(conn, owner_id, request_id, *, ignore_job=None):
    selection = latest(conn, "selections", request_id)
    if selection is None:
        raise ApiError(409, "SELECTION_REQUIRED")
    row = conn.execute(
        "SELECT * FROM comparisons WHERE id=%s", (selection["comparison_id"],)
    ).fetchone()
    comparison = comparison_view(conn, owner_id, row, ignore_job=ignore_job)
    source = next((s for s in comparison.sources if s.source_id == selection["source_id"]), None)
    if not comparison.current or source is None or not source.selectable:
        raise ApiError(412, "DECISION_CHANGED", "error.conflict")
    return selection, comparison


def approval_state(conn, row, *, ignore_job=None):
    if conn.execute(
        "SELECT 1 FROM approval_revocations WHERE approval_id=%s", (row["id"],)
    ).fetchone():
        return "revoked"
    at = jobs.clock(conn)
    if at < row["created_at"] or at >= row["expires_at"]:
        return "expired"
    session = conn.execute(
        "SELECT s.*,u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=%s",
        (row["session_id"],),
    ).fetchone()
    if (
        session is None
        or session["user_id"] != row["owner_id"]
        or not session["active"]
        or session["revoked_at"] is not None
        or at >= session["absolute_expires_at"]
        or not 0 <= at - session["last_seen_at"] < IDLE_MS
    ):
        return "invalidated"
    try:
        selection, comparison = selected_current(
            conn, row["owner_id"], row["request_id"], ignore_job=ignore_job
        )
    except ApiError:
        return "invalidated"
    if (
        selection["id"] != row["selection_id"]
        or comparison.packet_hash != row["packet_json"]["comparison_hash"]
    ):
        return "invalidated"
    # A newer approval supersedes an older one even for the same selection.
    if latest(conn, "approvals", row["request_id"])["id"] != row["id"]:
        return "invalidated"
    return "active"


def approval_view(conn, row, *, ignore_job=None):
    user = conn.execute(
        "SELECT id AS user_id,username,display_name FROM users WHERE id=%s",
        (row["owner_id"],),
    ).fetchone()
    return ApprovalView(
        id=row["id"],
        packet_hash=row["packet_hash"],
        selection_id=row["selection_id"],
        requester=user_view(user),
        created_at=iso_ms(row["created_at"]),
        expires_at=iso_ms(row["expires_at"]),
        state=approval_state(conn, row, ignore_job=ignore_job),
        scope=SCOPE,
    )


def approve(conn, owner_id, request_id, session, body, key):
    owned(conn, owner_id, request_id, lock=True)
    intent = content_hash(body.model_dump(mode="json"))
    prior = conn.execute(
        "SELECT * FROM approvals WHERE owner_id=%s AND request_id=%s AND idempotency_key=%s",
        (owner_id, request_id, key),
    ).fetchone()
    if prior:
        if prior["intent_hash"] != intent:
            raise ApiError(409, "IDEMPOTENCY_MISMATCH", "error.idempotency")
        return approval_view(conn, prior)
    at = jobs.clock(conn)
    if not 0 <= at - session["reauthenticated_at"] < REAUTH_MS:
        raise ApiError(401, "REAUTH_REQUIRED", "error.session")
    if conn.execute(
        "SELECT 1 FROM receipts WHERE request_id=%s AND request_version=%s",
        (request_id, body.request_version),
    ).fetchone():
        raise ApiError(409, "ALREADY_RELEASED")
    selection, comparison = selected_current(conn, owner_id, request_id)
    if body.scope_seen is not True:
        raise ApiError(422, "SCOPE_ACKNOWLEDGEMENT_REQUIRED")
    if (selection["id"], comparison.packet_hash, comparison.request_version) != (
        body.selection_id,
        body.comparison_hash,
        body.request_version,
    ):
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    packet = {
        "decision_schema": "approval-v1",
        "request_id": str(request_id),
        "request_version": body.request_version,
        "selection_id": str(selection["id"]),
        "selected_source_id": str(selection["source_id"]),
        "comparison_hash": comparison.packet_hash,
        "comparison": comparison.model_dump(mode="json"),
        "requester_id": str(owner_id),
        "requester": user_view(session).model_dump(mode="json"),
        "session_id": str(session["id"]),
        "approved_at": iso_ms(at),
        "expires_at": iso_ms(at + 600000),
        "scope": SCOPE,
    }
    row = conn.execute(
        "INSERT INTO approvals VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            uuid4(),
            request_id,
            body.request_version,
            selection["id"],
            owner_id,
            session["id"],
            Jsonb(packet),
            content_hash(packet),
            at,
            at + 600000,
            key,
            intent,
        ),
    ).fetchone()
    return approval_view(conn, row)


def revoke(conn, owner_id, approval_id):
    row = conn.execute(
        "SELECT * FROM approvals WHERE id=%s AND owner_id=%s", (approval_id, owner_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    owned(conn, owner_id, row["request_id"], lock=True)
    conn.execute(
        "INSERT INTO approval_revocations VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
        (approval_id, owner_id, jobs.clock(conn)),
    )
    return approval_view(conn, row)


def state(conn, owner_id, request_id):
    owned(conn, owner_id, request_id)
    c, s, a = [latest(conn, t, request_id) for t in ("comparisons", "selections", "approvals")]
    comparison = comparison_view(conn, owner_id, c) if c else None
    valid = False
    if s:
        try:
            valid = selected_current(conn, owner_id, request_id)[0]["id"] == s["id"]
        except ApiError:
            pass
    return DecisionView(
        comparison=comparison,
        selection=selection_view(s, valid) if s else None,
        approval=approval_view(conn, a) if a else None,
    )
