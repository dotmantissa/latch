"""Strict requester commands and server-owned decision views."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt

from services.common.source_policy import StrictRecord
from services.domain.contracts import UserView
from services.domain.rules import BasketResult

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Version = Annotated[StrictInt, Field(ge=1, le=2147483647)]


class CompareInput(StrictRecord):
    request_version: Version


class SelectionInput(StrictRecord):
    request_version: Version
    comparison_id: UUID
    comparison_hash: Hash
    source_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=0, le=1000)]


class ApprovalInput(StrictRecord):
    request_version: Version
    selection_id: UUID
    comparison_hash: Hash
    scope_seen: StrictBool


class ComparedSource(StrictRecord):
    source_id: UUID
    label: str
    capture_id: UUID
    extraction_id: UUID
    capture_hash: Hash
    content_fingerprint: Hash
    proposal_hash: Hash
    review_version: int
    review_set_hash: Hash
    correspondence_hash: Hash | None
    reviewed_fields: list[dict]
    profile_id: str
    profile_version: int
    basket: BasketResult
    blockers: list[str]
    selectable: bool
    rank: int | None = None


class ComparisonView(StrictRecord):
    id: UUID
    request_version: int
    packet_hash: Hash
    evaluated_at: str
    current: bool
    blockers: list[str]
    sources: list[ComparedSource]


class SelectionView(StrictRecord):
    id: UUID
    source_id: UUID
    comparison_id: UUID
    revision: int
    current: bool
    created_at: str


class ApprovalView(StrictRecord):
    id: UUID
    packet_hash: Hash
    selection_id: UUID
    requester: UserView
    created_at: str
    expires_at: str
    state: Literal["active", "expired", "revoked", "invalidated"]
    scope: str


class DecisionView(StrictRecord):
    comparison: ComparisonView | None
    selection: SelectionView | None
    approval: ApprovalView | None
