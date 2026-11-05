"""Independently validated source packet prepared before any database transaction."""

import base64
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from services.artifacts.sanitize import MAX_BYTES, Raster, sanitize
from services.artifacts.store import ArtifactStore
from services.common.captures import capture_artifact
from services.common.source_policy import SourceProfile
from services.domain.contracts import content_hash

FINGERPRINT_VERSION = "visible-text-v1"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    # Fixed whitespace normalization only. New clauses and unknown retained content survive.
    return "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")).strip()


def fingerprint(pages: list[dict], profile: SourceProfile) -> str:
    return content_hash({
        "projection_version": FINGERPRINT_VERSION,
        "profile": profile.model_dump(mode="json"),
        "pages": [{"url": page["url"], "text": normalize_text(page["text"])} for page in pages],
    })


@dataclass(frozen=True)
class Page:
    index: int
    url: str
    text: str
    text_hash: str
    started_at: datetime
    completed_at: datetime
    raster: Raster


@dataclass(frozen=True)
class Packet:
    capture_hash: str
    content_fingerprint: str
    profile_id: str
    profile_version: int
    pages: tuple[Page, ...]


def prepare(capture_bytes: bytes, profile: SourceProfile, url: str, store: ArtifactStore) -> Packet:
    # Capture admission is attributed to the recorded capture interval. Current profile activity
    # and job eligibility are checked again at the database write boundary.
    expected = [{"url": url}]
    if profile.terms_url:
        expected.append({"url": profile.terms_url})
    digest = capture_artifact(capture_bytes, {"pages": expected})
    capture = json.loads(capture_bytes)
    pages, total = [], 0
    for index, value in enumerate(capture["pages"]):
        start = datetime.fromisoformat(value["started_at"])
        end = datetime.fromisoformat(value["completed_at"])
        profile.admit(url, end)
        raw = base64.b64decode(
            capture["png_base64"] if index == 0 else value["png_base64"], validate=True,
        )
        raster = sanitize(raw)
        total += len(raster.data) + len(value["text"].encode())
        if total > MAX_BYTES:
            raise ValueError("SANITIZED_CAPTURE_CONTENT_LIMIT")
        pages.append(Page(
            index=index, url=value["url"], text=value["text"], text_hash=value["text_sha256"],
            started_at=start, completed_at=end, raster=raster,
        ))
    # Every page passed before admitting files. Interrupted DB work may leave private orphan
    # content-addressed files, never an authorized record pointing at a partial file.
    for page in pages:
        store.put(page.raster)
    return Packet(
        capture_hash=digest, content_fingerprint=fingerprint(capture["pages"], profile),
        profile_id=profile.id, profile_version=profile.version, pages=tuple(pages),
    )
