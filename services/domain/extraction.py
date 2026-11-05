"""Untrusted extraction proposals. Typed values and verbatim evidence never imply human review."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from services.common.source_policy import StrictRecord
from services.domain.contracts import Cents, Quantity, RequestItem, content_hash
from services.domain.rules import OfferLine, OfferTerms

EXTRACTION_SCHEMA_VERSION = "fields-v1"
PROMPT_VERSION = "public-terms-v1"
Reason = Literal[
    "source_absent", "conditional", "unreadable", "unsupported_basis", "conflicting_values"
]


class Quote(StrictRecord):
    page_index: Annotated[StrictInt, Field(ge=0, le=1)]
    quote: str = Field(min_length=1, max_length=1000)


class Evidence[T](StrictRecord):
    state: Literal["supported", "ambiguous", "unknown"]
    value: T | None
    evidence: list[Quote] = Field(max_length=4)
    reason: Reason | None

    @model_validator(mode="after")
    def support_shape(self):
        if self.state == "supported":
            if self.value is None or not self.evidence or self.reason is not None:
                raise ValueError("Supported proposals require a value and captured evidence")
        elif self.value is not None or self.reason is None:
            raise ValueError("Unresolved proposals must preserve null and a reason")
        if self.state == "ambiguous" and (
            len(self.evidence) < 2 or self.reason != "conflicting_values"
        ):
            raise ValueError("Ambiguity requires conflicting captured evidence")
        return self


Stock = Annotated[StrictInt, Field(ge=0, le=100_000_000)]
Price = Annotated[StrictInt, Field(ge=0, le=100_000_000)]


class ArrivalEvidence(Evidence[datetime]):
    @field_validator("value")
    @classmethod
    def explicit_time(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("An explicit source timezone is required")
        return value


class ProposedLine(StrictRecord):
    item_key: str = Field(pattern=r"^[a-zA-Z0-9_]{1,64}$")
    coverage: Evidence[Literal["quoted", "excluded"]]
    exact_match: Evidence[StrictBool]
    sell_unit_size: Evidence[Quantity]
    min_sell_units: Evidence[Quantity]
    price_cents: Evidence[Price]
    available_units: Evidence[Stock]


class ProposedTerms(StrictRecord):
    lines: list[ProposedLine] = Field(min_length=1, max_length=3)
    shipping_cents: Evidence[Cents]
    tax_included: Evidence[StrictBool]
    latest_arrival: ArrivalEvidence
    conditions_satisfied: Evidence[StrictBool]


class Span(StrictRecord):
    page_index: int
    start: int
    end: int
    quote: str
    capture_hash: str


class GroundedField(StrictRecord):
    item_key: str | None
    kind: str
    state: Literal["supported", "ambiguous", "unknown"]
    value: object | None
    reason: Reason | None
    spans: list[Span]


class Extraction(StrictRecord):
    source_id: UUID
    capture_hash: str
    schema_version: Literal["fields-v1"] = EXTRACTION_SCHEMA_VERSION
    prompt_version: Literal["public-terms-v1"] = PROMPT_VERSION
    model_id: str
    fields: list[GroundedField]
    proposal_hash: str


def public_items(items: list[RequestItem]) -> list[dict]:
    # This whitelist is the only projection permitted to reach inference.
    return [
        {
            "key": item.key,
            "public_specification": item.public_specification,
            "required_units": item.required_units,
        }
        for item in items
    ]


def ground(
    proposal: ProposedTerms,
    pages: list[dict],
    *,
    source_id: UUID,
    capture_hash: str,
    model_id: str,
    expected_item_keys: set[str],
) -> Extraction:
    keys = [line.item_key for line in proposal.lines]
    if len(set(keys)) != len(keys) or set(keys) != expected_item_keys:
        raise ValueError("Extraction must cover each exact public item key")
    if not re.fullmatch(r"[a-f0-9]{64}", capture_hash):
        raise ValueError("An actual capture byte hash is required")
    fields = []

    def append(kind, item_key, evidence):
        spans = []
        for quote in evidence.evidence:
            if quote.page_index >= len(pages):
                raise ValueError("Evidence page is outside this source capture")
            text = pages[quote.page_index]["text"]
            if text.count(quote.quote) != 1:
                raise ValueError("Evidence must resolve to one exact captured text span")
            start = text.index(quote.quote)
            spans.append(
                Span(
                    page_index=quote.page_index,
                    start=start,
                    end=start + len(quote.quote),
                    quote=quote.quote,
                    capture_hash=capture_hash,
                )
            )
        if evidence.state == "supported" and kind in ("price_cents", "shipping_cents"):
            amounts = set()
            for span in spans:
                for number in re.findall(
                    r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)(?![0-9.])", span.quote
                ):
                    whole, _, cents = number.replace(",", "").partition(".")
                    amounts.add(int(whole) * 100 + int(cents or "0"))
            if evidence.value not in amounts:
                raise ValueError("Money proposal must match a literal captured USD amount")
            if kind == "price_cents":
                nearby = set()
                for span in spans:
                    context = pages[span.page_index]["text"][
                        max(0, span.start - 80) : span.end + 80
                    ]
                    for number in re.findall(
                        r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)(?![0-9.,])", context
                    ):
                        whole, _, cents = number.replace(",", "").partition(".")
                        nearby.add(int(whole) * 100 + int(cents or "0"))
                if len(nearby) > 1:
                    raise ValueError("Nearby competing price amounts require unresolved review")
        fields.append(
            GroundedField(
                kind=kind,
                item_key=item_key,
                state=evidence.state,
                value=evidence.model_dump(mode="json")["value"],
                reason=evidence.reason,
                spans=spans,
            )
        )

    for line in sorted(proposal.lines, key=lambda item: item.item_key):
        for kind in (
            "coverage",
            "exact_match",
            "sell_unit_size",
            "min_sell_units",
            "price_cents",
            "available_units",
        ):
            append(kind, line.item_key, getattr(line, kind))
    for kind in ("shipping_cents", "tax_included", "latest_arrival", "conditions_satisfied"):
        append(kind, None, getattr(proposal, kind))
    payload = {
        "source_id": str(source_id),
        "capture_hash": capture_hash,
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_id": model_id,
        "fields": [f.model_dump(mode="json") for f in fields],
    }
    return Extraction(
        source_id=source_id,
        capture_hash=capture_hash,
        model_id=model_id,
        fields=fields,
        proposal_hash=content_hash(payload),
    )


def unreviewed_offer(extraction: Extraction) -> OfferTerms:
    lines, terms = {}, {}
    for field in extraction.fields:
        value = field.value if field.state == "supported" else None
        if field.item_key is None:
            terms[field.kind] = value
        else:
            lines.setdefault(field.item_key, {})[field.kind] = value
    return OfferTerms(
        source_id=str(extraction.source_id),
        lines=[
            OfferLine(
                item_key=key,
                coverage=value.get("coverage") or "unknown",
                exact_match=value.get("exact_match"),
                sell_unit_size=value.get("sell_unit_size"),
                min_sell_units=value.get("min_sell_units"),
                price_cents=value.get("price_cents"),
                available_units=value.get("available_units"),
                reviewed=False,
            )
            for key, value in sorted(lines.items())
        ],
        terms_reviewed=False,
        **terms,
    )
