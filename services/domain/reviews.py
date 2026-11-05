"""Trusted individual reviews; original model fields and source text remain immutable."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, TypeAdapter, model_validator

from services.common.source_policy import StrictRecord
from services.domain.contracts import Cents, Quantity
from services.domain.extraction import (
    Extraction,
    GroundedField,
    LineKind,
    Price,
    Quote,
    Span,
    Stock,
    TermKind,
    unreviewed_offer,
)
from services.domain.rules import OfferTerms

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ReviewInput(StrictRecord):
    request_version: Annotated[StrictInt, Field(ge=1)]
    expected_review_version: Annotated[StrictInt, Field(ge=0)]
    proposal_hash: Hash
    item_key: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{1,64}$")] | None
    kind: LineKind | TermKind
    action: Literal["confirm", "correct", "dispute"]
    corrected_value: object | None
    evidence: list[Quote] = Field(max_length=4)
    reason: str | None = Field(max_length=1000)
    evidence_seen: StrictBool

    @model_validator(mode="after")
    def individual_decision(self):
        if self.evidence_seen is not True:
            raise ValueError("The requester must acknowledge viewing this field's evidence")
        if self.action == "correct":
            if self.corrected_value is None or not self.evidence:
                raise ValueError("Corrections require a value and captured source evidence")
            typed_value(self.kind, self.corrected_value)
        elif self.corrected_value is not None:
            raise ValueError("Only a correction can supply a new value")
        if self.action in ("correct", "dispute") and (
            self.reason is None or len(self.reason.strip()) < 3
        ):
            raise ValueError("A correction or dispute requires a reason")
        return self


class Decision(StrictRecord):
    item_key: str | None
    kind: LineKind | TermKind
    action: Literal["confirm", "correct", "dispute"]
    state: Literal["buyer_checked", "disputed"]
    value: object | None
    reason: str | None
    spans: list[Span]


def typed_value(kind: str, value):
    types = {
        "coverage": Literal["quoted", "excluded"],
        "exact_match": StrictBool,
        "sell_unit_size": Quantity,
        "min_sell_units": Quantity,
        "price_cents": Price,
        "available_units": Stock,
        "shipping_cents": Cents,
        "tax_included": StrictBool,
        "conditions_satisfied": StrictBool,
    }
    if kind == "latest_arrival":
        if not isinstance(value, (str, datetime)):
            raise ValueError("Arrival correction requires an explicit timestamp")
        when = datetime.fromisoformat(value) if isinstance(value, str) else value
        if when.tzinfo is None:
            raise ValueError("Arrival correction requires a timezone")
        return when.isoformat()
    return TypeAdapter(types[kind]).validate_python(value)


def decide(
    original: GroundedField,
    body: ReviewInput,
    pages: list[dict],
    capture_hash: str,
) -> Decision:
    if (body.item_key, body.kind) != (original.item_key, original.kind):
        raise ValueError("A review must address one exact extracted field")
    spans = []
    for quote in body.evidence:
        if quote.page_index >= len(pages):
            raise ValueError("Review evidence is outside the captured source")
        text = pages[quote.page_index]["text"]
        if text.count(quote.quote) != 1:
            raise ValueError("Review evidence requires one exact captured quote")
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
    if body.action == "confirm":
        if original.state != "supported" or spans != original.spans:
            raise ValueError("Confirmation requires the supported original and its exact evidence")
        value = typed_value(original.kind, original.value)
    elif body.action == "correct":
        value = typed_value(original.kind, body.corrected_value)
        if body.kind in ("price_cents", "shipping_cents"):
            amounts = set()
            for span in spans:
                for number in re.findall(
                    r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)(?![0-9.])",
                    span.quote,
                ):
                    whole, _, cents = number.replace(",", "").partition(".")
                    amounts.add(int(whole) * 100 + int(cents or "0"))
            if value not in amounts:
                raise ValueError("A money correction must match a literal captured dollar amount")
            # Explicit named human correction may resolve a competing price basis, with a
            # reason and retained quotes. Model grounding never gets this authority.
    else:
        value = None
    return Decision(
        item_key=body.item_key,
        kind=body.kind,
        action=body.action,
        state="disputed" if body.action == "dispute" else "buyer_checked",
        value=value,
        reason=body.reason,
        spans=spans,
    )


def reviewed_offer(extraction: Extraction, decisions: list[Decision]) -> OfferTerms:
    by_key = {(d.item_key, d.kind): d for d in decisions}
    if len(by_key) != len(decisions):
        raise ValueError("Only the latest individual decision for each field is allowed")
    allowed = {(f.item_key, f.kind) for f in extraction.fields}
    if set(by_key) - allowed:
        raise ValueError("Review belongs to a different extraction")
    fields = []
    for field in extraction.fields:
        decision = by_key.get((field.item_key, field.kind))
        fields.append(
            field
            if decision is None
            else field.model_copy(
                update={
                    "value": decision.value,
                    "state": "supported" if decision.state == "buyer_checked" else "unknown",
                }
            )
        )
    proposal = extraction.model_copy(update={"fields": fields})
    offer = unreviewed_offer(proposal)

    def complete(item_key):
        return all(
            (d := by_key.get((f.item_key, f.kind))) is not None and d.state == "buyer_checked"
            for f in extraction.fields
            if f.item_key == item_key
        )

    return offer.model_copy(
        update={
            "lines": [
                line.model_copy(update={"reviewed": complete(line.item_key)})
                for line in offer.lines
            ],
            "terms_reviewed": complete(None),
        }
    )
