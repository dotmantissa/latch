"""Provisional schemas and evidence boundaries; no supplier outcome is simulated."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from services.domain.contracts import RequestItem
from services.domain.extraction import ProposedTerms, ground, public_items, unreviewed_offer
from services.runner.extraction import parse_proposal


def unresolved():
    return {"state": "unknown", "value": None, "evidence": [], "reason": "source_absent"}


def proposal():
    line = {"item_key": "assertion"} | {
        kind: unresolved()
        for kind in (
            "coverage",
            "exact_match",
            "sell_unit_size",
            "min_sell_units",
            "price_cents",
            "available_units",
        )
    }
    return {"lines": [line]} | {
        kind: unresolved()
        for kind in ("shipping_cents", "tax_included", "latest_arrival", "conditions_satisfied")
    }


def supported(value, quote):
    return {
        "state": "supported",
        "value": value,
        "evidence": [{"page_index": 0, "quote": quote}],
        "reason": None,
    }


def bind(data, text="Price assertion $12.34"):
    return ground(
        ProposedTerms.model_validate(data),
        [{"text": text}],
        source_id=uuid4(),
        capture_hash="a" * 64,
        model_id="assertion",
        expected_item_keys={"assertion"},
    )


def test_unknown_and_zero_remain_distinct_and_never_mark_reviewed():
    data = proposal()
    unknown = unreviewed_offer(bind(data))
    assert unknown.lines[0].price_cents is None and not unknown.lines[0].reviewed
    data["lines"][0]["price_cents"] = supported(0, "Price assertion $0.00")
    zero = unreviewed_offer(bind(data, "Price assertion $0.00"))
    assert zero.lines[0].price_cents == 0 and not zero.terms_reviewed
    assert zero.shipping_cents is None


@pytest.mark.parametrize("authority", ["reviewed", "approved", "feasible", "release_id"])
def test_model_cannot_create_authority(authority):
    data = proposal()
    data[authority] = True
    with pytest.raises(ValidationError):
        parse_proposal(json.dumps(data))


def test_quotes_money_foreign_keys_and_duplicate_json_are_rejected():
    data = proposal()
    data["lines"][0]["price_cents"] = supported(999, "Price assertion $12.34")
    with pytest.raises(ValueError):
        bind(data)
    data["lines"][0]["price_cents"] = supported(1234, "Absent assertion")
    with pytest.raises(ValueError):
        bind(data)
    data["lines"][0]["price_cents"] = supported(1234, "Price assertion $12.34")
    with pytest.raises(ValueError):
        bind(data, "Price assertion $12.34 and Price assertion $12.34")
    with pytest.raises(ValueError):
        bind(data, "Price assertion $12.34\nSurcharge assertion $15.00")
    data["lines"][0]["item_key"] = "foreign_item"
    with pytest.raises(ValueError):
        bind(data)
    with pytest.raises(ValueError):
        parse_proposal('{"lines":[],"lines":[]}')
    with pytest.raises(ValueError):
        parse_proposal('{"lines":NaN}')


def test_conflicting_amounts_remain_ambiguous_and_public_projection_excludes_notes():
    data = proposal()
    data["lines"][0]["price_cents"] = {
        "state": "ambiguous",
        "value": None,
        "evidence": [
            {"page_index": 0, "quote": "Base assertion $12.34"},
            {"page_index": 0, "quote": "Surcharge assertion $15.00"},
        ],
        "reason": "conflicting_values",
    }
    result = bind(data, "Base assertion $12.34\nSurcharge assertion $15.00")
    assert unreviewed_offer(result).lines[0].price_cents is None
    price = next(f for f in result.fields if f.kind == "price_cents")
    assert len(price.spans) == 2 and price.reason == "conflicting_values"
    item = RequestItem(
        key="assertion",
        specification="Internal purchasing note",
        public_specification="Public component specification",
        required_units=1,
    )
    payload = json.dumps(public_items([item]))
    assert "Internal purchasing note" not in payload and "Public component specification" in payload
    assert set(public_items([item])[0]) == {"key", "public_specification", "required_units"}
