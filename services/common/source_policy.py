"""Operator-reviewed source admission, not a browser-side network boundary."""

from datetime import UTC, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from services.common.urls import public_https_url, require_public_addresses  # noqa: F401


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceProfile(StrictRecord):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    version: StrictInt = Field(ge=1)
    origin: str
    offer_paths: list[str] = Field(min_length=1, max_length=10)
    terms_url: str | None = None
    main_selector: str = Field(min_length=1, max_length=300)
    terms_selector: str | None = Field(default=None, max_length=300)
    asset_origins: list[str] = Field(default_factory=list, max_length=10)
    expires_at: datetime

    @field_validator("origin")
    @classmethod
    def origin_only(cls, value: str) -> str:
        normalized = public_https_url(value)
        if urlsplit(normalized).path != "/":
            raise ValueError("Profile origin cannot contain a path")
        return normalized.rstrip("/")

    @field_validator("offer_paths")
    @classmethod
    def exact_paths(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if not path.startswith("/") or any(c in path for c in ("?", "#", "*", "\\")):
                raise ValueError("P0 uses explicitly reviewed exact offer paths")
            public_https_url("https://supplier.example.com" + path)
        return paths

    @field_validator("asset_origins")
    @classmethod
    def public_asset_origins(cls, origins: list[str]) -> list[str]:
        result = []
        for origin in origins:
            normalized = public_https_url(origin)
            if urlsplit(normalized).path != "/":
                raise ValueError("An asset origin cannot contain a path")
            result.append(normalized.rstrip("/"))
        return result

    @field_validator("terms_url")
    @classmethod
    def terms_public(cls, value: str | None) -> str | None:
        return public_https_url(value) if value else None

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Explicit timezone required")
        return value.astimezone(UTC)

    def admit(self, url: str, now: datetime) -> str:
        canonical = public_https_url(url)
        parsed = urlsplit(canonical)
        if now >= self.expires_at:
            raise ValueError("Source profile expired")
        if f"https://{parsed.hostname}" != self.origin or parsed.path not in self.offer_paths:
            raise ValueError("Unsupported supplier page")
        return canonical


class BuyerItem(StrictRecord):
    public_specification: str = Field(min_length=3, max_length=1000)
    required_units: StrictInt = Field(ge=1, le=10000)


class BuyerSource(StrictRecord):
    profile_id: str
    url: str


class BuyerTask(StrictRecord):
    """Private operator input. No invented example buyer task is supplied."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    name: str = Field(min_length=1, max_length=200)
    currency: str = Field(pattern=r"^USD$")
    budget_cents: StrictInt = Field(ge=1, le=100_000_000_000)
    required_by: datetime
    timezone: str
    delivery_basis: str = Field(min_length=3, max_length=500)
    items: list[BuyerItem] = Field(min_length=3, max_length=3)
    sources: list[BuyerSource] = Field(min_length=1, max_length=3)
    profiles: list[SourceProfile] = Field(min_length=1, max_length=3)
    public_html_task_confirmed: StrictBool
    consent_to_capture_and_inference: StrictBool

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("required_by")
    @classmethod
    def aware_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Explicit deadline timezone required")
        return value.astimezone(UTC)

    def admitted_sources(self, now: datetime) -> list[str]:
        if not self.public_html_task_confirmed or not self.consent_to_capture_and_inference:
            raise ValueError("Real task compatibility and capture/inference consent are required")
        if self.required_by <= now:
            raise ValueError("Buyer deadline has passed")
        profiles = {profile.id: profile for profile in self.profiles}
        if len(profiles) != len(self.profiles):
            raise ValueError("Duplicate profile IDs")
        sources = []
        for source in self.sources:
            if source.profile_id not in profiles:
                raise ValueError("Unknown source profile")
            sources.append(profiles[source.profile_id].admit(source.url, now))
        if len(set(sources)) != len(sources):
            raise ValueError("Duplicate source URL")
        return sources
