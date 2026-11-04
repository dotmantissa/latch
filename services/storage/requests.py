"""Owner-scoped immutable request revisions and atomic command recovery."""

from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from psycopg.types.json import Jsonb

from services.api.auth import iso_ms, now_ms
from services.api.errors import ApiError
from services.common.source_policy import SourceProfile
from services.domain.contracts import (
    RequestInput,
    RequestPage,
    RequestSummary,
    RequestView,
    UserView,
    content_hash,
)
from services.storage.database import lock_owner


def owned(conn, owner_id, request_id, *, lock=False):
    row = conn.execute(
        "SELECT * FROM requests WHERE id=%s AND owner_id=%s" + (" FOR UPDATE" if lock else ""),
        (request_id, owner_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    return row


def profiles(conn):
    rows = conn.execute(
        (
            "SELECT profile_json FROM source_profiles WHERE active=true AND "
            "expires_at>%s ORDER BY id,version DESC"
        ),
        (now_ms(),),
    ).fetchall()
    return [SourceProfile.model_validate(row["profile_json"]) for row in rows]


def admit_sources(conn, worksheet: RequestInput) -> None:
    for index, source in enumerate(worksheet.sources):
        row = conn.execute(
            (
                "SELECT profile_json FROM source_profiles WHERE id=%s AND version=%s "
                "AND active=true AND expires_at>%s FOR SHARE"
            ),
            (source.profile_id, source.profile_version, now_ms()),
        ).fetchone()
        try:
            if row is None:
                raise ValueError("Unknown source profile")
            SourceProfile.model_validate(row["profile_json"]).admit(source.url, datetime.now(UTC))
        except ValueError as exc:
            raise ApiError(
                422,
                "UNSUPPORTED_SOURCE",
                "error.source",
                fields={f"sources.{index}.url": "error.source"},
            ) from exc


def view(conn, owner_id, request_id, version: int | None = None) -> RequestView:
    request = owned(conn, owner_id, request_id)
    version = request["current_version"] if version is None else version
    row = conn.execute(
        "SELECT * FROM request_versions WHERE request_id=%s AND version=%s", (request_id, version)
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    user = conn.execute(
        "SELECT id,username,display_name FROM users WHERE id=%s", (owner_id,)
    ).fetchone()
    snapshot = dict(row["snapshot_json"])
    cents = snapshot.pop("budget_cents")
    snapshot["budget"] = f"{cents // 100}.{cents % 100:02}"
    return RequestView(
        id=str(request_id),
        reference=f"LCH{request['seq']:05}",
        owner=UserView(
            id=str(user["id"]), username=user["username"], display_name=user["display_name"]
        ),
        version=version,
        status="archived" if request["archived_at"] else "draft",
        saved_at=iso_ms(row["created_at"]),
        content_hash=row["content_hash"],
        worksheet=RequestInput.model_validate(snapshot),
    )


def listing(conn, owner_id, cursor: int | None, limit: int) -> RequestPage:
    rows = conn.execute(
        (
            "SELECT r.*,v.snapshot_json->>'name' AS name FROM requests r JOIN "
            "request_versions v ON v.request_id=r.id AND "
            "v.version=r.current_version WHERE owner_id=%s AND (%s::bigint IS NULL "
            "OR seq<%s) ORDER BY seq DESC LIMIT %s"
        ),
        (owner_id, cursor, cursor, limit + 1),
    ).fetchall()
    page = rows[:limit]
    return RequestPage(
        requests=[
            RequestSummary(
                id=str(row["id"]),
                reference=f"LCH{row['seq']:05}",
                name=row["name"],
                version=row["current_version"],
                status="archived" if row["archived_at"] else "draft",
                saved_at=iso_ms(row["updated_at"]),
            )
            for row in page
        ],
        next_cursor=page[-1]["seq"] if len(rows) > limit else None,
    )


def insert_version(conn, owner_id, request_id, version: int, worksheet: RequestInput) -> None:
    snapshot, at = worksheet.snapshot(), now_ms()
    conn.execute(
        "INSERT INTO request_versions VALUES(%s,%s,%s,%s,%s)",
        (request_id, version, Jsonb(snapshot), content_hash(snapshot), at),
    )
    for position, item in enumerate(worksheet.items):
        conn.execute(
            "INSERT INTO required_items VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                request_id,
                version,
                item.key,
                item.specification,
                item.public_specification,
                item.required_units,
                position,
            ),
        )
    for source in worksheet.sources:
        conn.execute(
            "INSERT INTO supplier_sources VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                request_id,
                version,
                source.label,
                source.url,
                source.profile_id,
                source.profile_version,
                urlsplit(source.url).hostname,
            ),
        )
    conn.execute(
        "UPDATE requests SET current_version=%s,updated_at=%s WHERE id=%s",
        (version, at, request_id),
    )
    conn.execute(
        (
            "INSERT INTO events(owner_id,request_id,kind,safe_payload_json,at) "
            "VALUES(%s,%s,'request_saved',%s,%s)"
        ),
        (owner_id, request_id, Jsonb({"version": version}), at),
    )


def replay(conn, owner_id, scope: str, key: str, intent: str):
    row = conn.execute(
        "SELECT * FROM idempotency WHERE owner_id=%s AND route_scope=%s AND key=%s",
        (owner_id, scope, key),
    ).fetchone()
    if row is None:
        return None
    # Keys cannot silently perform another command after expiry: require a new key.
    if row["intent_hash"] != intent:
        raise ApiError(409, "IDEMPOTENCY_MISMATCH", "error.idempotency")
    return view(conn, owner_id, row["resource_id"], row["resource_version"])


def remember(conn, owner_id, scope: str, key: str, intent: str, result: RequestView, status: int):
    at = now_ms()
    conn.execute(
        "INSERT INTO idempotency VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (owner_id, scope, key, intent, result.id, result.version, status, at, at + 86400000),
    )


def save(
    conn,
    owner_id,
    worksheet: RequestInput,
    key: str,
    *,
    request_id=None,
    expected: int | None = None,
) -> RequestView:
    lock_owner(conn, str(owner_id))
    scope = f"requests/{request_id}" if request_id else "requests/create"
    intent = content_hash({"worksheet": worksheet.snapshot(), "expected": expected})
    prior = replay(conn, owner_id, scope, key, intent)
    if prior:
        return prior
    admit_sources(conn, worksheet)
    if worksheet.required_by <= datetime.now(UTC):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "error.deadline",
            fields={"required_by_local": "error.deadline"},
        )
    if request_id:
        current = owned(conn, owner_id, request_id, lock=True)
        if current["archived_at"]:
            raise ApiError(409, "ARCHIVED_REQUEST", "error.archived")
        if expected != current["current_version"]:
            raise ApiError(
                412,
                "VERSION_PRECONDITION",
                "error.conflict",
                current_version=current["current_version"],
            )
        version = expected + 1
    else:
        request_id, version, at = uuid4(), 1, now_ms()
        conn.execute(
            (
                "INSERT INTO requests(id,owner_id,current_version,created_at,updated_at"
                ") VALUES(%s,%s,1,%s,%s)"
            ),
            (request_id, owner_id, at, at),
        )
    insert_version(conn, owner_id, request_id, version, worksheet)
    result = view(conn, owner_id, request_id)
    remember(conn, owner_id, scope, key, intent, result, 200 if expected else 201)
    return result


def archive(conn, owner_id, request_id, expected: int) -> RequestView:
    lock_owner(conn, str(owner_id))
    row = owned(conn, owner_id, request_id, lock=True)
    if row["current_version"] != expected:
        raise ApiError(
            412, "VERSION_PRECONDITION", "error.conflict", current_version=row["current_version"]
        )
    if not row["archived_at"]:
        at = now_ms()
        conn.execute(
            "UPDATE requests SET archived_at=%s,updated_at=%s WHERE id=%s", (at, at, request_id)
        )
        conn.execute(
            (
                "INSERT INTO events(owner_id,request_id,kind,safe_payload_json,at) "
                "VALUES(%s,%s,'request_archived','{}',%s)"
            ),
            (owner_id, request_id, at),
        )
    return view(conn, owner_id, request_id)
