"""Adversarial attribution checks, separate from actual source accuracy."""

from uuid import uuid4

import pytest

from services.domain.correspondence import ProposedCorrespondence, blockers, ground, validate


def fixture():
    pages = [
        {"text": "Actual literal quote", "sanitized_hash": "a" * 64, "width": 50, "height": 40}
    ]
    proposal = ProposedCorrespondence(
        observations=[
            {
                "page_index": 0,
                "item_key": None,
                "status": "agrees",
                "reason": "visible_match",
                "evidence": [{"page_index": 0, "quote": "literal quote"}],
                "region": [0, 0, 50, 40],
            },
            {
                "page_index": 0,
                "item_key": "item",
                "status": "abstains",
                "reason": "not_visible",
                "evidence": [],
                "region": None,
            },
        ]
    )
    result = ground(
        proposal,
        source_id=uuid4(),
        capture_hash="b" * 64,
        pages=pages,
        item_keys={"item"},
        model_id="assertion",
    )
    return result, pages


def test_abstention_is_visible_and_never_purchasing_authority():
    result, pages = fixture()
    validate(result, pages, {"item"})
    assert blockers(result) == ["IMAGE_CORRESPONDENCE_UNRESOLVED"]
    assert blockers(None) == ["IMAGE_CORRESPONDENCE_MISSING"]
    with pytest.raises(ValueError):
        ProposedCorrespondence.model_validate(dict(result.model_dump(), approved=True))


@pytest.mark.parametrize("mutation", ["raster", "text", "region", "item", "hash"])
def test_attribution_fails_closed(mutation):
    result, pages = fixture()
    if mutation == "raster":
        pages[0]["sanitized_hash"] = "c" * 64
    elif mutation == "text":
        pages[0]["text"] = "Other quote"
    elif mutation == "region":
        pages[0]["width"] = 49
    elif mutation == "item":
        with pytest.raises(ValueError):
            validate(result, pages, {"other"})
        return
    else:
        result = result.model_copy(update={"result_hash": "d" * 64})
    with pytest.raises(ValueError):
        validate(result, pages, {"item"})
