"""Pure bounded basket calculation; arithmetic checks are not live supplier evidence."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StrictBool, field_validator

from services.common.source_policy import StrictRecord
from services.domain.contracts import MAX_TOTAL, Cents, Quantity

POLICY_VERSION = "basket-v1"


class OfferLine(StrictRecord):
    item_key: str
    coverage: Literal["quoted", "excluded", "unknown"]
    exact_match: StrictBool | None = None
    sell_unit_size: Quantity | None = None
    min_sell_units: Quantity | None = None
    price_cents: Annotated[int, Field(strict=True, ge=0, le=100_000_000)] | None = None
    available_units: Annotated[int, Field(strict=True, ge=0, le=100_000_000)] | None = None
    reviewed: StrictBool = False


class OfferTerms(StrictRecord):
    source_id: str
    lines: list[OfferLine] = Field(min_length=1, max_length=3)
    shipping_cents: Cents | None = None
    tax_included: StrictBool | None = None
    latest_arrival: datetime | None = None
    conditions_satisfied: StrictBool | None = None
    terms_reviewed: StrictBool = False

    @field_validator("latest_arrival")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Explicit arrival timezone required")
        return value


class BasketResult(StrictRecord):
    source_id: str
    quoted_subtotal_cents: int
    complete_total_cents: int | None
    complete: bool
    reviewed: bool
    feasible: bool
    reasons: list[str]
    lines: list[dict[str, str | int | None]]
    policy_version: str = POLICY_VERSION


def calculate_basket(
    required: dict[str, int],
    offer: OfferTerms,
    budget_cents: int,
    deadline: datetime,
    now: datetime,
) -> BasketResult:
    if not 1 <= len(required) <= 3 or any(
        type(q) is not int or not 1 <= q <= 10000 for q in required.values()
    ):
        raise ValueError("Invalid required quantities")
    if type(budget_cents) is not int or not 1 <= budget_cents <= MAX_TOTAL:
        raise ValueError("Invalid budget")
    if deadline.tzinfo is None or now.tzinfo is None:
        raise ValueError("Explicit timestamps required")
    by_key = {line.item_key: line for line in offer.lines}
    if len(by_key) != len(offer.lines) or set(by_key) - set(required):
        raise ValueError("Offer lines must reference distinct required items")
    subtotal, complete, reviewed = 0, True, offer.terms_reviewed
    reasons, lines = [], []
    for key, quantity in sorted(required.items()):
        line = by_key.get(key)
        if line is None or line.coverage != "quoted":
            complete = False
            reasons.append(f"{key}:MISSING_LINE")
            lines.append({"item_key": key, "sell_units": None, "extended_cents": None})
            continue
        reviewed = reviewed and line.reviewed
        if any(
            value is None for value in (line.sell_unit_size, line.min_sell_units, line.price_cents)
        ):
            complete = False
            reasons.append(f"{key}:UNKNOWN_PRICE_BASIS")
            lines.append({"item_key": key, "sell_units": None, "extended_cents": None})
            continue
        sell_units = max(
            line.min_sell_units, (quantity + line.sell_unit_size - 1) // line.sell_unit_size
        )
        delivered = sell_units * line.sell_unit_size
        extended = sell_units * line.price_cents
        subtotal += extended
        if subtotal > MAX_TOTAL:
            raise ValueError("Aggregate exceeds supported bounds")
        lines.append(
            {
                "item_key": key,
                "sell_units": sell_units,
                "delivered_units": delivered,
                "extended_cents": extended,
            }
        )
        if line.exact_match is not True:
            reasons.append(
                f"{key}:ITEM_MISMATCH" if line.exact_match is False else f"{key}:UNKNOWN_MATCH"
            )
        if line.available_units is None:
            reasons.append(f"{key}:UNKNOWN_AVAILABILITY")
        elif line.available_units < delivered:
            reasons.append(f"{key}:INSUFFICIENT_STOCK")
    total = (
        subtotal + offer.shipping_cents
        if complete and offer.shipping_cents is not None and offer.tax_included is True
        else None
    )
    if total is not None and total > MAX_TOTAL:
        raise ValueError("Aggregate exceeds supported bounds")
    complete = complete and total is not None
    if offer.shipping_cents is None:
        reasons.append("UNKNOWN_SHIPPING")
    if offer.tax_included is not True:
        reasons.append("UNSUPPORTED_TAX")
    if offer.latest_arrival is None:
        reasons.append("UNKNOWN_DELIVERY")
    elif offer.latest_arrival > deadline or offer.latest_arrival < now:
        reasons.append("DELIVERY_NOT_FEASIBLE")
    if deadline <= now:
        reasons.append("DEADLINE_PASSED")
    if offer.conditions_satisfied is not True:
        reasons.append("UNCONFIRMED_CONDITIONS")
    if total is not None and total > budget_cents:
        reasons.append("OVER_BUDGET")
    if not reviewed:
        reasons.append("REVIEW_REQUIRED")
    return BasketResult(
        source_id=offer.source_id,
        quoted_subtotal_cents=subtotal,
        complete_total_cents=total,
        complete=complete,
        reviewed=reviewed,
        feasible=complete and reviewed and not reasons,
        reasons=reasons,
        lines=lines,
    )
