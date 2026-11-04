"""Versioned public request contracts and canonical hashing."""

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictInt, field_validator, model_validator

from services.common.source_policy import StrictRecord, public_https_url

SCHEMA_VERSION = 1
MAX_TOTAL = 100_000_000_000
Quantity = Annotated[StrictInt, Field(ge=1, le=10000)]
Cents = Annotated[StrictInt, Field(ge=0, le=MAX_TOTAL)]


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def content_hash(value: object) -> str:
    return hashlib.sha256(
        canonical_json({"schema_version": SCHEMA_VERSION, "value": value}).encode()
    ).hexdigest()


def utc_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def money_cents(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?", value
    ):
        raise ValueError("Enter a USD amount with at most two decimal places")
    cents = int(Decimal(value) * 100)
    if not 1 <= cents <= MAX_TOTAL:
        raise ValueError("Amount is outside the supported range")
    return cents


class RequestItem(StrictRecord):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    specification: str = Field(min_length=3, max_length=1000)
    public_specification: str = Field(min_length=3, max_length=1000)
    required_units: Quantity

    @field_validator("specification", "public_specification")
    @classmethod
    def meaningful_specification(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Enter the required specification")
        return value


class RequestSource(StrictRecord):
    label: str = Field(min_length=1, max_length=100)
    url: str
    profile_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    profile_version: Annotated[StrictInt, Field(ge=1)]

    _url = field_validator("url")(public_https_url)


class RequestInput(StrictRecord):
    name: str = Field(min_length=1, max_length=200)
    currency: Literal["USD"] = "USD"
    budget: str
    required_by: datetime
    timezone: str = Field(max_length=100)
    required_by_local: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    delivery_basis: str = Field(min_length=3, max_length=500)
    items: list[RequestItem] = Field(min_length=1, max_length=3)
    sources: list[RequestSource] = Field(default_factory=list, max_length=3)

    @field_validator("name", "delivery_basis")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field is required")
        return value.strip()

    @field_validator("budget")
    @classmethod
    def decimal_budget(cls, value: str) -> str:
        money_cents(value)
        return value

    @field_validator("required_by")
    @classmethod
    def explicit_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.microsecond % 1000:
            raise ValueError("An explicit timezone and millisecond precision are required")
        return value.astimezone(UTC)

    @field_validator("required_by", mode="before")
    @classmethod
    def timestamp_type(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("An ISO timestamp with an explicit timezone is required")
        return value

    @model_validator(mode="after")
    def consistent(self) -> "RequestInput":
        try:
            zone = ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Choose an IANA timezone") from exc
        # Round-trip to catch DST gaps and a client that submits another zone's instant.
        if self.required_by.astimezone(zone).strftime("%Y-%m-%dT%H:%M") != self.required_by_local:
            raise ValueError("The local deadline does not match its timezone and UTC instant")
        local = datetime.fromisoformat(self.required_by_local)
        if local.replace(tzinfo=zone, fold=0).utcoffset() != local.replace(
            tzinfo=zone, fold=1
        ).utcoffset():
            raise ValueError("Choose an unambiguous local deadline")
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("Item keys must be unique")
        if len({source.url for source in self.sources}) != len(self.sources):
            raise ValueError("Supplier pages must be unique")
        return self

    def snapshot(self) -> dict:
        data = self.model_dump(mode="json")
        data["budget_cents"] = money_cents(data.pop("budget"))
        data["required_by"] = utc_string(self.required_by)
        return data

    def material_hash(self) -> str:
        snapshot = self.snapshot()
        snapshot["items"] = sorted(snapshot["items"], key=lambda item: item["key"])
        snapshot["sources"] = sorted(
            snapshot["sources"],
            key=lambda source: (source["profile_id"], source["profile_version"], source["url"]),
        )
        return content_hash(snapshot)


class UserView(StrictRecord):
    id: str
    username: str
    display_name: str


class SessionView(StrictRecord):
    user: UserView
    csrf_token: str
    expires_at: str
    reauth_fresh: bool


class ProfileView(StrictRecord):
    id: str
    version: int
    origin: str
    offer_paths: list[str]
    expires_at: str


class RequestView(StrictRecord):
    id: str
    reference: str
    owner: UserView
    version: int
    status: Literal["draft", "archived"]
    saved_at: str
    content_hash: str
    worksheet: RequestInput


class RequestSummary(StrictRecord):
    id: str
    reference: str
    name: str
    version: int
    status: Literal["draft", "archived"]
    saved_at: str


class RequestPage(StrictRecord):
    requests: list[RequestSummary]
    next_cursor: int | None


class ErrorView(StrictRecord):
    code: str
    message_key: str
    field_errors: dict[str, str] = Field(default_factory=dict)
    retryable: bool = False
    correlation_id: str
    current_version: int | None = None
