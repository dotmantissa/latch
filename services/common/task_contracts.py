"""Strict task identifiers and fixed source command shared across the private channel."""

from uuid import UUID

from pydantic import Field, StrictInt

from services.common.source_policy import StrictRecord


class TaskRef(StrictRecord):
    job_id: UUID
    fence: UUID


class TaskCommand(TaskRef):
    task_id: UUID
    profile_id: str = Field(min_length=1, max_length=100)
    profile_version: StrictInt = Field(ge=1)
    url: str = Field(max_length=2000)
