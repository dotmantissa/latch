"""Authorized captured evidence, with raw file paths and private provider usage excluded."""

from typing import Literal
from uuid import UUID

from services.common.source_policy import StrictRecord
from services.domain.extraction import Extraction


class CapturedPageView(StrictRecord):
    artifact_id: UUID
    page_index: int
    source_url: str
    source_text: str
    text_hash: str
    started_at: str
    completed_at: str
    sanitized_hash: str
    width: int
    height: int


class CaptureView(StrictRecord):
    id: UUID
    source_id: UUID
    request_version: int
    capture_hash: str
    content_fingerprint: str
    profile_id: str
    profile_version: int
    review_state: Literal["unreviewed"] = "unreviewed"
    pages: list[CapturedPageView]
    extraction_id: UUID | None
    extraction: Extraction | None
