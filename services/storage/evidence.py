"""Immutable capture attribution and provisional extraction, guarded by active job fences."""

import hashlib
from uuid import uuid4

from psycopg.types.json import Jsonb

from services.api.auth import iso_ms
from services.api.errors import ApiError
from services.artifacts.contracts import CapturedPageView, CaptureView
from services.artifacts.packet import FINGERPRINT_VERSION, Packet
from services.artifacts.sanitize import POLICY_VERSION
from services.domain.extraction import Extraction, revalidate
from services.storage import jobs
from services.storage.requests import owned


def current(conn, job_id, fence, holder, *, renew=False):
    job = (jobs.heartbeat if renew else jobs.leased)(conn, job_id, fence, holder)
    request = owned(conn, job["owner_id"], job["request_id"], lock=True)
    if (jobs.clock(conn) >= job["deadline_at"] or job["cancel_requested_at"]
            or request["archived_at"]
            or request["current_version"] != job["request_version"]):
        raise ValueError("EVIDENCE_JOB_NO_LONGER_CURRENT")
    return job


def active_profile(conn, profile_id, profile_version):
    profile = conn.execute(
        "SELECT * FROM source_profiles WHERE id=%s AND version=%s FOR SHARE",
        (profile_id, profile_version),
    ).fetchone()
    if profile is None or not profile["active"] or profile["expires_at"] <= jobs.clock(conn):
        raise ValueError("EVIDENCE_PROFILE_NO_LONGER_ACTIVE")
    return profile["expires_at"]


def validate_usage(extraction: Extraction, usage: dict):
    if (not isinstance(usage, dict) or set(usage) != {"calls", "attempts", "capture_sha256"}
            or type(usage["calls"]) is not int or not 1 <= usage["calls"] <= 3
            or not isinstance(usage["attempts"], list)
            or len(usage["attempts"]) != usage["calls"]
            or usage["capture_sha256"] != extraction.capture_hash):
        raise ValueError("EVIDENCE_EXTRACTION_USAGE_INVALID")
    for attempt in usage["attempts"]:
        if (not isinstance(attempt, dict) or set(attempt) != {"model", "usage", "elapsed_ms"}
                or attempt["model"] != extraction.model_id
                or type(attempt["elapsed_ms"]) is not int or attempt["elapsed_ms"] < 0):
            raise ValueError("EVIDENCE_EXTRACTION_USAGE_INVALID")
        counts = attempt["usage"]
        if (not isinstance(counts, dict)
                or set(counts) != {"prompt_tokens", "completion_tokens", "total_tokens"}
                or any(type(n) is not int or n < 0 for n in counts.values())
                or counts["completion_tokens"] > 4096
                or counts["total_tokens"] != counts["prompt_tokens"] + counts["completion_tokens"]):
            raise ValueError("EVIDENCE_EXTRACTION_USAGE_INVALID")


def save_capture(conn, job_id, fence, holder, task_id, packet: Packet):
    job = current(conn, job_id, fence, holder)
    task = conn.execute(
        "SELECT t.*,s.request_id,s.version,s.profile_id,s.profile_version,p.active,p.expires_at "
        "FROM job_tasks t JOIN supplier_sources s ON s.id=t.source_id JOIN source_profiles p "
        "ON p.id=s.profile_id AND p.version=s.profile_version "
        "WHERE t.task_id=%s AND t.job_id=%s AND t.fence=%s FOR SHARE OF p",
        (task_id, job_id, fence),
    ).fetchone()
    at = jobs.clock(conn)
    if (task is None or task["request_id"] != job["request_id"]
            or task["version"] != job["request_version"] or not task["cleanup_at"]
            or task["outcome"] != "captured" or task["artifact_hash"] != packet.capture_hash
            or (task["profile_id"], task["profile_version"]) != (
                packet.profile_id, packet.profile_version)
            or not task["active"] or task["expires_at"] <= at):
        raise ValueError("EVIDENCE_CAPTURE_ATTRIBUTION_INVALID")
    if not 1 <= len(packet.pages) <= 2 or [p.index for p in packet.pages] != list(
            range(len(packet.pages))):
        raise ValueError("EVIDENCE_PAGE_SET_INVALID")
    for page in packet.pages:
        if (page.text_hash != hashlib.sha256(page.text.encode()).hexdigest()
                or page.raster.sanitizer_version != POLICY_VERSION
                or int(page.started_at.timestamp() * 1000) < task["started_at"] - 2000
                or int(page.completed_at.timestamp() * 1000) > at + 2000):
            raise ValueError("EVIDENCE_PAGE_ATTRIBUTION_INVALID")
    previous = conn.execute("SELECT * FROM source_captures WHERE task_id=%s", (task_id,)).fetchone()
    if previous:
        if (previous["capture_hash"] != packet.capture_hash
                or previous["content_fingerprint"] != packet.content_fingerprint):
            raise ValueError("EVIDENCE_IDEMPOTENCY_MISMATCH")
        return previous
    row = conn.execute(
        "INSERT INTO source_captures(id,owner_id,request_id,request_version,job_id,fence,task_id,"
        "source_id,capture_hash,content_fingerprint,fingerprint_version,profile_id,profile_version,"
        "page_count,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (uuid4(), job["owner_id"], job["request_id"], job["request_version"], job_id, fence,
         task_id,
         task["source_id"], packet.capture_hash, packet.content_fingerprint, FINGERPRINT_VERSION,
         packet.profile_id, packet.profile_version, len(packet.pages), at),
    ).fetchone()
    for page in packet.pages:
        conn.execute(
            "INSERT INTO captured_pages VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uuid4(), row["id"], page.index, page.url, page.text, page.text_hash,
             int(page.started_at.timestamp() * 1000), int(page.completed_at.timestamp() * 1000),
             page.raster.raw_hash, page.raster.sanitized_hash, len(page.raster.data),
             page.raster.width, page.raster.height, POLICY_VERSION),
        )
    jobs.event(conn, job, "capture_stored")
    return row


def save_extraction(conn, job_id, fence, holder, capture_id, extraction: Extraction, usage: dict):
    current(conn, job_id, fence, holder)
    capture = conn.execute(
        "SELECT * FROM source_captures WHERE id=%s AND job_id=%s AND fence=%s",
        (capture_id, job_id, fence),
    ).fetchone()
    if (capture is None or extraction.source_id != capture["source_id"]
            or extraction.capture_hash != capture["capture_hash"]):
        raise ValueError("EVIDENCE_EXTRACTION_ATTRIBUTION_INVALID")
    active_profile(conn, capture["profile_id"], capture["profile_version"])
    validate_usage(extraction, usage)
    pages = conn.execute(
        "SELECT source_text AS text FROM captured_pages WHERE capture_id=%s ORDER BY page_index",
        (capture_id,),
    ).fetchall()
    keys = conn.execute(
        "SELECT stable_item_key FROM required_items WHERE request_id=%s AND version=%s",
        (capture["request_id"], capture["request_version"]),
    ).fetchall()
    revalidate(extraction, pages, {item["stable_item_key"] for item in keys})
    prior = conn.execute(
        "SELECT * FROM source_extractions WHERE capture_id=%s", (capture_id,),
    ).fetchone()
    if prior:
        if prior["proposal_hash"] != extraction.proposal_hash:
            raise ValueError("EVIDENCE_EXTRACTION_IDEMPOTENCY_MISMATCH")
        return prior
    row = conn.execute(
        "INSERT INTO source_extractions VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
        (uuid4(), capture_id, Jsonb(extraction.model_dump(mode="json")), extraction.proposal_hash,
         Jsonb(usage), jobs.clock(conn)),
    ).fetchone()
    job = current(conn, job_id, fence, holder)
    jobs.event(conn, job, "extraction_stored")
    return row


def complete_set(conn, job):
    """Revalidate the whole fenced packet at publication, including current profiles."""
    sources = conn.execute(
        "SELECT * FROM supplier_sources WHERE request_id=%s AND version=%s ORDER BY id",
        (job["request_id"], job["request_version"]),
    ).fetchall()
    captures = conn.execute(
        "SELECT c.*,e.proposal_json,e.proposal_hash,e.usage_json FROM source_captures c "
        "JOIN source_extractions e ON e.capture_id=c.id "
        "WHERE c.job_id=%s AND c.fence=%s ORDER BY c.source_id",
        (job["id"], job["fence"]),
    ).fetchall()
    if (not 1 <= len(sources) <= 3 or len(captures) != len(sources)
            or {c["source_id"] for c in captures} != {s["id"] for s in sources}):
        raise ValueError("COMPLETE_EXTRACTION_SET_REQUIRED")
    profiles = conn.execute(
        "SELECT p.active,p.expires_at FROM source_profiles p JOIN supplier_sources s "
        "ON p.id=s.profile_id AND p.version=s.profile_version "
        "WHERE s.request_id=%s AND s.version=%s ORDER BY p.id,p.version FOR SHARE OF p",
        (job["request_id"], job["request_version"]),
    ).fetchall()
    if len(profiles) != len(sources) or any(not p["active"] for p in profiles):
        raise ValueError("EVIDENCE_PROFILE_NO_LONGER_ACTIVE")
    valid_until = min(p["expires_at"] for p in profiles)
    keys = {row["stable_item_key"] for row in conn.execute(
        "SELECT stable_item_key FROM required_items WHERE request_id=%s AND version=%s",
        (job["request_id"], job["request_version"]),
    ).fetchall()}
    pages = conn.execute(
        "SELECT capture_id,page_index,source_text AS text FROM captured_pages "
        "WHERE capture_id=ANY(%s) ORDER BY capture_id,page_index",
        ([capture["id"] for capture in captures],),
    ).fetchall()
    source_by_id = {source["id"]: source for source in sources}
    for capture in captures:
        source = source_by_id[capture["source_id"]]
        extraction = Extraction.model_validate(capture["proposal_json"])
        captured_pages = [p for p in pages if p["capture_id"] == capture["id"]]
        if (extraction.source_id != capture["source_id"]
                or extraction.capture_hash != capture["capture_hash"]
                or extraction.proposal_hash != capture["proposal_hash"]
                or (capture["profile_id"], capture["profile_version"]) != (
                    source["profile_id"], source["profile_version"])
                or len(captured_pages) != capture["page_count"]
                or [p["page_index"] for p in captured_pages] != list(range(capture["page_count"]))):
            raise ValueError("EVIDENCE_EXTRACTION_ATTRIBUTION_INVALID")
        validate_usage(extraction, capture["usage_json"])
        revalidate(extraction, captured_pages, keys)
    return valid_until


def artifact(conn, owner_id, artifact_id):
    # An abandoned fence or partial/failed job never publishes its provisional files.
    row = conn.execute(
        "SELECT p.sanitized_png_hash,p.sanitized_bytes,p.width,p.height,p.sanitizer_version "
        "FROM captured_pages p JOIN source_captures c ON c.id=p.capture_id "
        "JOIN jobs j ON j.id=c.job_id AND j.fence=c.fence "
        "WHERE p.id=%s AND c.owner_id=%s AND j.state='succeeded'",
        (artifact_id, owner_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    return row


def list_captures(conn, owner_id, request_id, version):
    owned(conn, owner_id, request_id)
    return conn.execute(
        "SELECT c.* FROM source_captures c JOIN jobs j ON j.id=c.job_id AND j.fence=c.fence "
        "WHERE c.owner_id=%s AND c.request_id=%s AND c.request_version=%s "
        "AND j.state='succeeded' AND j.kind='inspect' "
        "AND j.id=(SELECT id FROM jobs WHERE owner_id=%s AND request_id=%s "
        "AND request_version=%s AND kind='inspect' AND state='succeeded' "
        "ORDER BY finished_at DESC,id DESC LIMIT 1) ORDER BY c.source_id",
        (owner_id, request_id, version, owner_id, request_id, version),
    ).fetchall()


def views(conn, owner_id, request_id, version):
    results = []
    for capture in list_captures(conn, owner_id, request_id, version):
        pages = conn.execute(
            "SELECT * FROM captured_pages WHERE capture_id=%s ORDER BY page_index",
            (capture["id"],),
        ).fetchall()
        proposal = conn.execute(
            "SELECT id,proposal_json FROM source_extractions WHERE capture_id=%s", (capture["id"],),
        ).fetchone()
        results.append(CaptureView(
            id=capture["id"], source_id=capture["source_id"],
            request_version=capture["request_version"], capture_hash=capture["capture_hash"],
            content_fingerprint=capture["content_fingerprint"], profile_id=capture["profile_id"],
            profile_version=capture["profile_version"],
            pages=[CapturedPageView(
                artifact_id=p["id"], page_index=p["page_index"], source_url=p["source_url"],
                source_text=p["source_text"], text_hash=p["text_hash"],
                started_at=iso_ms(p["started_at"]), completed_at=iso_ms(p["completed_at"]),
                sanitized_hash=p["sanitized_png_hash"], width=p["width"], height=p["height"],
            ) for p in pages],
            extraction_id=proposal["id"] if proposal else None,
            extraction=Extraction.model_validate(proposal["proposal_json"]) if proposal else None,
        ))
    return results
