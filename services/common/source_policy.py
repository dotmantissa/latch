"""Operator-reviewed source admission, not a browser-side network boundary."""

import ipaddress
import re
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def public_https_url(value: str) -> str:
    if len(value) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ValueError("Invalid public source address")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Only public HTTPS URLs without credentials or queries are supported")
    host = parsed.hostname
    if host.endswith(".") or "%" in host or ":" in host:
        raise ValueError("Noncanonical hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literal sources are unsupported")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
        raise ValueError("Noncanonical hostname")
    # Numeric alternate address encodings and local-only names are not supplier hosts.
    if "." not in host or all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", x) for x in host.split(".")):
        raise ValueError("Public DNS hostname required")
    if host.endswith((".local", ".localhost", ".internal", ".test", ".invalid")):
        raise ValueError("Reserved hostname")
    decoded = unquote(parsed.path)
    if "%" in decoded or re.search(r"[\\\x00-\x1f\x7f]", decoded):
        raise ValueError("Encoded navigation is unsupported")
    if any(part in (".", "..") for part in decoded.split("/")):
        raise ValueError("Noncanonical source path")
    return f"https://{host}{parsed.path or '/'}"


def require_public_addresses(addresses: list[str]) -> tuple[str, ...]:
    """The proxy must apply this to every DNS answer and pin at socket connection."""
    if not addresses:
        raise ValueError("No resolved address")
    normalized = []
    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if parsed.version == 6 and parsed.ipv4_mapped:
            parsed = parsed.ipv4_mapped
        if not parsed.is_global:
            raise ValueError("Private or reserved destination denied")
        normalized.append(str(parsed))
    return tuple(normalized)


class SourceProfile(StrictRecord):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    version: StrictInt = Field(ge=1)
    origin: str
    offer_paths: list[str] = Field(min_length=1, max_length=10)
    terms_url: str | None = None
    main_selector: str = Field(min_length=1, max_length=300)
    terms_selector: str | None = Field(default=None, max_length=300)
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
            public_https_url("https://supplier.example" + path)
        return paths

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
