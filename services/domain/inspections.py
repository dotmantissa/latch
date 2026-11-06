"""User-visible execution status and bounded public-only inspection planning."""

from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool

from services.common.source_policy import StrictRecord
from services.domain.contracts import JobView


class InspectInput(StrictRecord):
    current_version: int = Field(strict=True, ge=1)
    public_scope_seen: StrictBool


class InspectionView(StrictRecord):
    request_version: int
    enabled: bool
    reason: str | None
    job: JobView | None


class ProposedPlan(StrictRecord):
    source_order: list[UUID] = Field(min_length=1, max_length=3)
    workflow: Literal["capture_extract_verify"]
