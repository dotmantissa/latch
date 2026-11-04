"""Mathematical boundary assertions, separate from live supplier acceptance."""

import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from services.domain.contracts import RequestInput, content_hash, money_cents
from services.domain.rules import OfferLine, OfferTerms, calculate_basket


def worksheet_data():
    deadline = (datetime.now(UTC) + timedelta(days=7)).replace(second=0, microsecond=0)
    return {
        "name": "Domain boundary assertion",
        "budget": "100.00",
        "required_by": deadline.isoformat(),
        "timezone": "UTC",
        "required_by_local": deadline.strftime("%Y-%m-%dT%H:%M"),
        "delivery_basis": "Calendar deadline in the specified timezone",
        "items": [
            {
                "key": "item_1",
                "specification": "Boundary assertion",
                "public_specification": "Public boundary assertion",
                "required_units": 25,
            }
        ],
        "sources": [],
    }


@pytest.mark.parametrize(
    "value", ["0", "-1", "1e3", "1.005", "NaN", " 1", "1,000", "01", 1.5, True]
)
def test_budget_rejects_ambiguous_or_unbounded_values(value):
    with pytest.raises(ValueError):
        money_cents(value)


def test_decimal_and_hash_are_stable_across_processes():
    assert money_cents("0.01") == 1
    assert money_cents("999999999.99") == 99999999999
    a = content_hash({"b": None, "a": 0})
    assert a != content_hash({"a": 0})
    script = (
        "from services.domain.contracts import content_hash; print(content_hash({'a':0,'b':None}))"
    )
    assert subprocess.check_output([sys.executable, "-c", script], text=True).strip() == a


def test_deadline_zone_and_strict_mutation_fields():
    data = worksheet_data()
    data["timezone"] = "Africa/Lagos"
    with pytest.raises(ValidationError):
        RequestInput.model_validate(data)
    data = worksheet_data()
    data["approved"] = True
    with pytest.raises(ValidationError):
        RequestInput.model_validate(data)


def terms(**changes):
    now = datetime.now(UTC)
    args = dict(
        source_id="arithmetic_assertion",
        lines=[
            OfferLine(
                item_key="item_1",
                coverage="quoted",
                exact_match=True,
                sell_unit_size=10,
                min_sell_units=1,
                price_cents=100,
                available_units=30,
                reviewed=True,
            )
        ],
        shipping_cents=0,
        tax_included=True,
        latest_arrival=now + timedelta(days=1),
        conditions_satisfied=True,
        terms_reviewed=True,
    )
    args.update(changes)
    return OfferTerms(**args)


def test_pack_rounding_shipping_zero_and_missing_line():
    now = datetime.now(UTC)
    result = calculate_basket({"item_1": 25}, terms(), 300, now + timedelta(days=2), now)
    assert result.feasible and result.complete_total_cents == 300
    assert result.lines[0]["sell_units"] == 3 and result.lines[0]["delivered_units"] == 30
    result = calculate_basket(
        {"item_1": 25, "item_2": 1}, terms(), 300, now + timedelta(days=2), now
    )
    assert result.complete_total_cents is None and result.quoted_subtotal_cents == 300
    assert not result.complete and not result.feasible
    result = calculate_basket(
        {"item_1": 25}, terms(shipping_cents=None), 300, now + timedelta(days=2), now
    )
    assert result.complete_total_cents is None


def test_review_and_temporal_feasibility_never_inferred():
    now = datetime.now(UTC)
    for offer in [
        terms(terms_reviewed=False),
        terms(conditions_satisfied=None),
        terms(tax_included=None),
        terms(latest_arrival=None),
    ]:
        assert not calculate_basket(
            {"item_1": 25}, offer, 300, now + timedelta(days=2), now
        ).feasible
    result = calculate_basket({"item_1": 25}, terms(), 299, now + timedelta(days=2), now)
    assert "OVER_BUDGET" in result.reasons
    result = calculate_basket({"item_1": 25}, terms(), 300, now - timedelta(seconds=1), now)
    assert "DEADLINE_PASSED" in result.reasons
