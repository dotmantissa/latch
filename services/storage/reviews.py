"""Append-only owner review commands with exact extraction and request version preconditions."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from services.api.auth import iso_ms
from services.api.errors import ApiError
from services.common.source_policy import StrictRecord
from services.domain.contracts import UserView, content_hash
from services.domain.extraction import Extraction, GroundedField
from services.domain.reviews import Decision, ReviewInput, decide, reviewed_offer
from services.domain.rules import BasketResult, calculate_basket
from services.storage import jobs
from services.storage.requests import owned


class ReviewView(StrictRecord):
    id: UUID
    version: int
    reviewer: UserView
    created_at: str
    decision: Decision


class FieldView(StrictRecord):
    original: GroundedField
    state: Literal["extracted", "unknown", "disputed", "buyer_checked"]
    value: object | None
    latest_review: ReviewView | None


class SourceReviewView(StrictRecord):
    extraction_id: UUID
    capture_id: UUID
    request_id: UUID
    request_version: int
    current: bool
    review_allowed: bool
    review_blocker: Literal["packet_changed", "inspection_active", "profile_unavailable"] | None
    review_version: int
    review_set_hash: str
    checked_fields: int
    total_fields: int
    fields: list[FieldView]
    basket: BasketResult | None


class ReviewPage(StrictRecord):
    items: list[ReviewView]
    next_before: int | None


def source(conn, owner_id, extraction_id):
    row = conn.execute(
        "SELECT e.id AS extraction_id,e.proposal_json,c.*,j.finished_at "
        "FROM source_extractions e JOIN source_captures c ON c.id=e.capture_id "
        "JOIN jobs j ON j.id=c.job_id AND j.fence=c.fence "
        "WHERE e.id=%s AND c.owner_id=%s AND j.state='succeeded' AND j.kind='inspect'",
        (extraction_id, owner_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    return row


def row_view(conn, row):
    user = conn.execute(
        "SELECT id,username,display_name FROM users WHERE id=%s", (row["reviewer_id"],)
    ).fetchone()
    return ReviewView(
        id=row["id"],
        version=row["version"],
        reviewer=UserView(
            id=str(user["id"]),
            username=user["username"],
            display_name=user["display_name"],
        ),
        created_at=iso_ms(row["created_at"]),
        decision=Decision.model_validate(row["decision_json"]),
    )


def is_current(conn, capture, request):
    latest = conn.execute(
        "SELECT id FROM jobs WHERE owner_id=%s AND request_id=%s AND request_version=%s "
        "AND kind='inspect' AND state='succeeded' ORDER BY finished_at DESC,id DESC LIMIT 1",
        (capture["owner_id"], capture["request_id"], capture["request_version"]),
    ).fetchone()
    return (
        request["current_version"] == capture["request_version"]
        and not request["archived_at"]
        and latest is not None
        and latest["id"] == capture["job_id"]
    )


def save(conn, owner_id, extraction_id, body: ReviewInput, key: str):
    capture = source(conn, owner_id, extraction_id)
    request = owned(conn, owner_id, capture["request_id"], lock=True)
    intent = content_hash(
        {"extraction_id": str(extraction_id), "command": body.model_dump(mode="json")}
    )
    prior = conn.execute(
        "SELECT * FROM field_reviews WHERE extraction_id=%s AND reviewer_id=%s "
        "AND idempotency_key=%s",
        (extraction_id, owner_id, key),
    ).fetchone()
    if prior:
        if prior["intent_hash"] != intent:
            raise ApiError(409, "IDEMPOTENCY_MISMATCH", "error.idempotency")
        return row_view(conn, prior)
    if body.request_version != capture["request_version"] or not is_current(conn, capture, request):
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    if conn.execute(
        "SELECT 1 FROM jobs WHERE request_id=%s AND state IN "
        "('queued','running','recovering','cancelling')",
        (capture["request_id"],),
    ).fetchone():
        raise ApiError(409, "INSPECTION_ACTIVE", "error.conflict")
    profile = conn.execute(
        "SELECT active,expires_at FROM source_profiles WHERE id=%s AND version=%s FOR SHARE",
        (capture["profile_id"], capture["profile_version"]),
    ).fetchone()
    if not profile["active"] or profile["expires_at"] <= jobs.clock(conn):
        raise ApiError(422, "SOURCE_PROFILE_EXPIRED", "error.source")
    extraction = Extraction.model_validate(capture["proposal_json"])
    if body.proposal_hash != extraction.proposal_hash:
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
    conn.execute("INSERT INTO review_heads VALUES(%s,0) ON CONFLICT DO NOTHING", (extraction_id,))
    head = conn.execute(
        "SELECT version FROM review_heads WHERE extraction_id=%s FOR UPDATE", (extraction_id,)
    ).fetchone()["version"]
    if head != body.expected_review_version:
        raise ApiError(412, "VERSION_PRECONDITION", "error.conflict", current_version=head)
    if head >= 1000:
        raise ApiError(429, "REVIEW_LIMIT")
    original = next(
        (f for f in extraction.fields if (f.item_key, f.kind) == (body.item_key, body.kind)), None
    )
    pages = conn.execute(
        "SELECT source_text AS text FROM captured_pages WHERE capture_id=%s ORDER BY page_index",
        (capture["id"],),
    ).fetchall()
    try:
        if original is None:
            raise ValueError("Unknown field")
        decision = decide(original, body, pages, capture["capture_hash"])
    except (ValueError, TypeError, KeyError):
        raise ApiError(422, "REVIEW_EVIDENCE_INVALID") from None
    row = conn.execute(
        "INSERT INTO field_reviews VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            uuid4(),
            extraction_id,
            head + 1,
            owner_id,
            body.request_version,
            body.proposal_hash,
            Jsonb(decision.model_dump(mode="json")),
            Jsonb(body.model_dump(mode="json")),
            key,
            intent,
            jobs.clock(conn),
        ),
    ).fetchone()
    conn.execute(
        "UPDATE review_heads SET version=%s WHERE extraction_id=%s", (head + 1, extraction_id)
    )
    conn.execute(
        "INSERT INTO events(owner_id,request_id,kind,safe_payload_json,at) "
        "VALUES(%s,%s,'field_reviewed',%s,%s)",
        (
            owner_id,
            capture["request_id"],
            Jsonb(
                {
                    "extraction_id": str(extraction_id),
                    "review_version": head + 1,
                }
            ),
            jobs.clock(conn),
        ),
    )
    return row_view(conn, row)


def view(conn, owner_id, extraction_id):
    capture = source(conn, owner_id, extraction_id)
    request = owned(conn, owner_id, capture["request_id"])
    extraction = Extraction.model_validate(capture["proposal_json"])
    rows = conn.execute(
        "SELECT DISTINCT ON (decision_json->>'item_key',decision_json->>'kind') * "
        "FROM field_reviews WHERE extraction_id=%s "
        "ORDER BY decision_json->>'item_key',decision_json->>'kind',version DESC",
        (extraction_id,),
    ).fetchall()
    latest = [row_view(conn, row) for row in rows]
    by_key = {(r.decision.item_key, r.decision.kind): r for r in latest}
    head = conn.execute(
        "SELECT version FROM review_heads WHERE extraction_id=%s", (extraction_id,)
    ).fetchone()
    fields = []
    for field in extraction.fields:
        review = by_key.get((field.item_key, field.kind))
        state = (
            review.decision.state
            if review
            else {
                "supported": "extracted",
                "ambiguous": "disputed",
                "unknown": "unknown",
            }[field.state]
        )
        value = review.decision.value if review else field.value
        fields.append(FieldView(original=field, state=state, value=value, latest_review=review))
    snapshot = conn.execute(
        "SELECT snapshot_json FROM request_versions WHERE request_id=%s AND version=%s",
        (capture["request_id"], capture["request_version"]),
    ).fetchone()["snapshot_json"]
    basket = None
    if {"items", "budget_cents", "required_by"} <= set(snapshot):
        basket = calculate_basket(
            {item["key"]: item["required_units"] for item in snapshot["items"]},
            reviewed_offer(extraction, [r.decision for r in latest]),
            snapshot["budget_cents"],
            datetime.fromisoformat(snapshot["required_by"]),
            datetime.fromtimestamp(jobs.clock(conn) / 1000, UTC),
        )
    current = is_current(conn, capture, request)
    blocker = None
    if not current:
        blocker = "packet_changed"
    elif conn.execute(
        "SELECT 1 FROM jobs WHERE request_id=%s AND state IN "
        "('queued','running','recovering','cancelling')",
        (capture["request_id"],),
    ).fetchone():
        blocker = "inspection_active"
    else:
        profile = conn.execute(
            "SELECT active,expires_at FROM source_profiles WHERE id=%s AND version=%s",
            (capture["profile_id"], capture["profile_version"]),
        ).fetchone()
        if not profile or not profile["active"] or profile["expires_at"] <= jobs.clock(conn):
            blocker = "profile_unavailable"
    return SourceReviewView(
        extraction_id=extraction_id,
        capture_id=capture["id"],
        request_id=capture["request_id"],
        request_version=capture["request_version"],
        current=current,
        review_allowed=blocker is None,
        review_blocker=blocker,
        review_version=head["version"] if head else 0,
        review_set_hash=content_hash(
            {
                "proposal_hash": extraction.proposal_hash,
                "review_ids": sorted(str(r.id) for r in latest),
            }
        ),
        checked_fields=sum(f.state == "buyer_checked" for f in fields),
        total_fields=len(fields),
        fields=fields,
        basket=basket,
    )


def history(conn, owner_id, extraction_id, before: int | None, limit: int):
    source(conn, owner_id, extraction_id)
    rows = conn.execute(
        "SELECT * FROM field_reviews WHERE extraction_id=%s AND version<%s "
        "ORDER BY version DESC LIMIT %s",
        (extraction_id, before if before else 10001, limit + 1),
    ).fetchall()
    return ReviewPage(
        items=[row_view(conn, r) for r in rows[:limit]],
        next_before=rows[limit - 1]["version"] if len(rows) > limit else None,
    )
