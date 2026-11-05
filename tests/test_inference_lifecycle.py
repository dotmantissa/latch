"""Adversarial local HTTP lifecycle assertions, never simulated supplier acceptance."""

import asyncio
import hashlib
import json
import time
from uuid import uuid4

import httpx
import pytest

from services.common.config import Settings
from services.domain.contracts import RequestItem
from services.runner.extraction import extract
from services.runner.vultr import ProviderFailure, VultrClient
from services.storage.evidence import validate_usage
from services.storage.jobs import FenceLost
from tests.test_extraction import bind, proposal


@pytest.fixture
def client(tmp_path):
    key = tmp_path / "credential"
    key.write_text("local_lifecycle_assertion")
    key.chmod(0o600)
    return VultrClient(Settings(model_id="assertion", inference_key_file=key))


def transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "services.runner.vultr.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


def response(content="{}", **changes):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    } | changes)


def test_public_http_input_budgets_and_metadata(client, monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return response()

    transport(monkeypatch, handler)
    message, usage = client.complete([{"role": "user", "content": "public assertion"}])
    assert message == {"content": "{}"}
    assert set(usage) == {"model", "usage", "elapsed_ms"}
    assert seen[0]["max_tokens"] == 1024
    assert "local_lifecycle_assertion" not in json.dumps(seen)
    for _ in range(2):
        client.complete([])
    with pytest.raises(ProviderFailure, match="CALL_LIMIT"):
        client.complete([])
    assert len(seen) == 3


def test_expired_or_cancelled_admission_spends_no_call(client, monkeypatch):
    transport(monkeypatch, lambda request: pytest.fail("No HTTP request permitted"))
    with pytest.raises(ProviderFailure, match="DEADLINE_EXPIRED"):
        client.complete([], deadline=time.monotonic() - 1)

    def cancelled():
        raise ValueError("INSPECTION_CANCELLED")

    with pytest.raises(ValueError, match="INSPECTION_CANCELLED"):
        client.complete([], checkpoint=cancelled)
    assert client.calls == 0


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), True, "unbounded"])
def test_invalid_deadline_spends_no_call(client, deadline):
    with pytest.raises(ProviderFailure, match="DEADLINE_INVALID"):
        client.complete([], deadline=deadline)
    assert client.calls == 0


def test_pending_headers_cancel_on_fence_loss_and_close_request(client, monkeypatch):
    observed = []

    async def handler(request):
        observed.append("started")
        try:
            await asyncio.sleep(30)
        finally:
            observed.append("closed")

    transport(monkeypatch, handler)
    checkpoints = []

    def check():
        checkpoints.append(time.monotonic())
        if len(checkpoints) == 2:
            raise FenceLost("JOB_FENCE_LOST")

    started = time.monotonic()
    with pytest.raises(FenceLost):
        client.complete([], checkpoint=check)
    assert 4 <= time.monotonic() - started < 8
    assert observed == ["started", "closed"] and client.calls == 1


class Trickle(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        while True:
            await asyncio.sleep(0.01)
            yield b" "

    async def aclose(self):
        self.closed = True


def test_trickling_response_has_absolute_deadline_and_closes(client, monkeypatch):
    stream = Trickle()
    transport(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    started = time.monotonic()
    with pytest.raises(ProviderFailure, match="DEADLINE_EXPIRED"):
        client.complete([], deadline=started + 0.15)
    assert time.monotonic() - started < 1 and stream.closed


@pytest.mark.parametrize("payload,code", [
    ({"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 4}}, "USAGE"),
    ({"usage": {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3}}, "USAGE"),
    ({"usage": {"prompt_tokens": 1, "completion_tokens": 1025, "total_tokens": 1026}}, "USAGE"),
    ({"choices": [{"message": {}, "finish_reason": "length"}]}, "INCOMPLETE"),
    ({"choices": []}, "SCHEMA"),
])
def test_bad_provider_shape_counts_and_truncation_fail_closed(client, monkeypatch, payload, code):
    transport(monkeypatch, lambda request: response(**payload))
    with pytest.raises(ProviderFailure, match=code):
        client.complete([])


@pytest.mark.parametrize("first_finish", ["stop", "length"])
def test_repair_has_one_shared_deadline_and_public_item_context(client, monkeypatch, first_finish):
    import services.runner.extraction as extraction_module

    monkeypatch.setattr(
        extraction_module, "capture_artifact", lambda raw, _: hashlib.sha256(raw).hexdigest(),
    )
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        if len(seen) == 1 and first_finish == "length":
            # Even valid-looking JSON marked truncated must never be accepted directly.
            return response(choices=[{
                "message": {"content": json.dumps(proposal())}, "finish_reason": "length",
            }])
        return response("invalid" if len(seen) == 1 else json.dumps(proposal()))

    transport(monkeypatch, handler)
    deadlines = []
    complete = client.complete

    def recorded(*args, **kwargs):
        deadlines.append(kwargs["deadline"])
        return complete(*args, **kwargs)

    monkeypatch.setattr(client, "complete", recorded)
    item = RequestItem(
        key="assertion", specification="private note sentinel",
        public_specification="public component", required_units=1,
    )
    result, usage = extract(
        client, json.dumps({"pages": [{"url": "https://vendor.example.com/offer",
                                      "text": "public source"}]}).encode(),
        source_id=uuid4(), items=[item], expected_pages=[{}],
    )
    assert usage["calls"] == 2 and len(set(deadlines)) == 1
    assert "private note sentinel" not in json.dumps(seen)
    assert json.loads(seen[0]["messages"][1]["content"])["items"] == [{
        "key": "assertion", "public_specification": "public component", "required_units": 1,
    }]
    assert all(field.value is None for field in result.fields)
    validate_usage(result, usage)
    with pytest.raises(ValueError):
        validate_usage(result, usage | {"provider_answer": "not permitted"})


def test_usage_model_hash_call_count_and_private_fields_are_rejected():
    result = bind(proposal())
    usage = {"calls": 1, "capture_sha256": "a" * 64, "attempts": [{
        "model": "assertion", "elapsed_ms": 1,
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }]}
    validate_usage(result, usage)
    for changed in (
        usage | {"calls": True}, usage | {"calls": 4}, usage | {"capture_sha256": "b" * 64},
        usage | {"attempts": []},
        usage | {"attempts": [usage["attempts"][0] | {"model": "foreign"}]},
        usage | {"attempts": [usage["attempts"][0] | {"private": "not permitted"}]},
    ):
        with pytest.raises(ValueError):
            validate_usage(result, changed)
