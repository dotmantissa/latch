"""Pure individual review boundaries; no generated supplier or human acceptance outcome."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from services.domain.reviews import ReviewInput, decide, reviewed_offer
from services.domain.rules import calculate_basket
from tests.test_extraction import bind, proposal, supported


def review(field, *, action="confirm", value=None, quotes=None, reason=None):
    return ReviewInput(
        request_version=1,
        expected_review_version=0,
        proposal_hash="a" * 64,
        item_key=field.item_key,
        kind=field.kind,
        action=action,
        corrected_value=value,
        evidence=quotes
        if quotes is not None
        else [{"page_index": s.page_index, "quote": s.quote} for s in field.spans],
        reason=reason,
        evidence_seen=True,
    )


def test_unknown_ambiguous_acknowledgement_and_authority_fail_closed():
    extraction = bind(proposal())
    field = next(f for f in extraction.fields if f.kind == "price_cents")
    with pytest.raises(ValueError):
        decide(field, review(field), [{"text": "Price assertion $12.34"}], "a" * 64)
    for body in (
        review(field, action="dispute", reason="Missing source value").model_dump()
        | {"evidence_seen": False},
        review(field, action="dispute", reason="Missing source value").model_dump()
        | {"evidence_seen": 1},
        review(field, action="dispute", reason="Missing source value").model_dump()
        | {"approved": True},
    ):
        with pytest.raises(ValidationError):
            ReviewInput.model_validate(body)


def test_human_money_resolution_requires_reason_type_and_exact_capture():
    data = proposal()
    data["lines"][0]["price_cents"] = {
        "state": "ambiguous",
        "value": None,
        "reason": "conflicting_values",
        "evidence": [
            {"page_index": 0, "quote": "Base assertion $12.34"},
            {"page_index": 0, "quote": "Surcharge assertion $15.00"},
        ],
    }
    text = "Base assertion $12.34\nSurcharge assertion $15.00"
    extraction = bind(data, text)
    field = next(f for f in extraction.fields if f.kind == "price_cents")
    for value, quote in (
        (1200, "Base assertion $12.34"),
        ("1500", "Surcharge assertion $15.00"),
        (True, "Surcharge assertion $15.00"),
        (1500, "Absent assertion $15.00"),
    ):
        with pytest.raises(ValueError):
            decide(
                field,
                review(
                    field,
                    action="correct",
                    value=value,
                    quotes=[{"page_index": 0, "quote": quote}],
                    reason="Source basis",
                ),
                [{"text": text}],
                "a" * 64,
            )
    decision = decide(
        field,
        review(
            field,
            action="correct",
            value=1500,
            quotes=[
                {
                    "page_index": 0,
                    "quote": "Surcharge assertion $15.00",
                }
            ],
            reason="Explicit surcharge basis",
        ),
        [{"text": text}],
        "a" * 64,
    )
    assert decision.state == "buyer_checked" and decision.value == 1500
    assert field.state == "ambiguous" and field.value is None
    offer = reviewed_offer(extraction, [decision])
    assert offer.lines[0].price_cents == 1500 and not offer.lines[0].reviewed
    assert offer.shipping_cents is None and not offer.terms_reviewed
    outcome = calculate_basket(
        {"assertion": 1},
        offer,
        10000,
        datetime(2027, 1, 1, tzinfo=UTC),
        datetime(2026, 11, 5, tzinfo=UTC),
    )
    assert not outcome.feasible and outcome.complete_total_cents is None


def test_confirmation_cannot_swap_evidence_and_dispute_removes_value_without_rewriting():
    data = proposal()
    data["lines"][0]["price_cents"] = supported(1234, "Price assertion $12.34")
    original = bind(data)
    field = next(f for f in original.fields if f.kind == "price_cents")
    confirmed = decide(field, review(field), [{"text": "Price assertion $12.34"}], "a" * 64)
    assert confirmed.value == 1234
    with pytest.raises(ValueError):
        decide(
            field,
            review(field, quotes=[{"page_index": 0, "quote": "$12.34"}]),
            [{"text": "Price assertion $12.34"}],
            "a" * 64,
        )
    disputed = decide(
        field,
        review(field, action="dispute", reason="Unclear pack price basis"),
        [{"text": "Price assertion $12.34"}],
        "a" * 64,
    )
    assert reviewed_offer(original, [disputed]).lines[0].price_cents is None
    assert field.value == 1234 and field.state == "supported"
    with pytest.raises(ValueError):
        reviewed_offer(original, [confirmed, disputed])


def test_unknown_shipping_cannot_become_free_without_literal_zero_evidence():
    extraction = bind(proposal())
    shipping = next(f for f in extraction.fields if f.kind == "shipping_cents")
    with pytest.raises(ValueError):
        decide(
            shipping,
            review(
                shipping,
                action="correct",
                value=0,
                quotes=[{"page_index": 0, "quote": "Conditional free shipping"}],
                reason="Assertion correction",
            ),
            [{"text": "Conditional free shipping"}],
            "a" * 64,
        )
    zero = decide(
        shipping,
        review(
            shipping,
            action="correct",
            value=0,
            quotes=[{"page_index": 0, "quote": "Shipping assertion $0.00"}],
            reason="Explicit zero source amount",
        ),
        [{"text": "Shipping assertion $0.00"}],
        "a" * 64,
    )
    assert zero.value == 0 and shipping.value is None
