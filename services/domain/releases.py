"""Source differences and immutable internal release contracts."""

import difflib
from typing import Literal
from uuid import UUID

from pydantic import StrictBool

from services.common.source_policy import StrictRecord
from services.domain.decisions import Hash, Version


class ReleaseInput(StrictRecord):
    request_version: Version
    approval_id: UUID
    approval_hash: Hash
    scope_seen: StrictBool


class SourceDiff(StrictRecord):
    source_id: UUID
    old_capture_id: UUID
    new_capture_id: UUID
    text_changed: bool
    raster_changed: bool
    old_fingerprint: Hash
    new_fingerprint: Hash
    text_diff: list[str]


class ReleaseAttemptView(StrictRecord):
    id: UUID
    request_id: UUID
    request_version: int
    approval_id: UUID
    job_id: UUID
    state: Literal["queued", "running", "changed", "blocked", "released"]
    reason: str | None
    differences: list[SourceDiff]
    receipt_id: UUID | None
    created_at: str


class ReceiptView(StrictRecord):
    id: UUID
    request_id: UUID
    request_version: int
    committed_at: str
    record_hash: Hash
    record: dict


def source_diff(old, new, old_pages, new_pages):
    text_changed = old["content_fingerprint"] != new["content_fingerprint"]
    raster_changed = [p["sanitized_png_hash"] for p in old_pages] != [
        p["sanitized_png_hash"] for p in new_pages
    ]
    # Fixed normalization only; clauses stay visible. Bound display, never acceptance.
    from services.artifacts.packet import normalize_text

    a = "\n".join(normalize_text(p["source_text"]) for p in old_pages).splitlines()
    b = "\n".join(normalize_text(p["source_text"]) for p in new_pages).splitlines()
    lines, total = [], 0
    for line in difflib.unified_diff(
        a, b, fromfile="approved capture", tofile="fresh capture", n=2
    ):
        if len(lines) >= 100 or total + len(line.encode()) > 16384:
            lines.append("Additional changes remain in the captured source text.")
            break
        lines.append(line.rstrip("\n"))
        total += len(line.encode())
    return SourceDiff(
        source_id=old["source_id"],
        old_capture_id=old["id"],
        new_capture_id=new["id"],
        text_changed=text_changed,
        raster_changed=raster_changed,
        old_fingerprint=old["content_fingerprint"],
        new_fingerprint=new["content_fingerprint"],
        text_diff=lines,
    )
