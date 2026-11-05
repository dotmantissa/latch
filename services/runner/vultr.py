"""Bounded Vultr capability client. This module has no purchasing authority."""

import asyncio
import json
import math
import time

import httpx

from services.common.config import Settings, read_secret


class ProviderFailure(Exception):
    """A safe code, never a raw provider response or credential."""


class ProviderIncomplete(ProviderFailure):
    """A truncated response can request a bounded formatting repair, never be accepted."""

    def __init__(self, message, usage):
        super().__init__("PROVIDER_INCOMPLETE_RESPONSE")
        self.message = {"content": (message.get("content") or "").encode()[:20 * 1024].decode(
            "utf-8", "ignore",
        )}
        self.unexpected_tools = bool(message.get("tool_calls"))
        self.usage = usage


class VultrClient:
    def __init__(self, settings: Settings, *, output_token_limit: int = 1024):
        if not settings.model_id or settings.inference_key_file is None:
            raise ProviderFailure("INFERENCE_NOT_CONFIGURED")
        self.model_id = settings.model_id
        self.endpoint = settings.inference_base_url + "/chat/completions"
        self._key = read_secret(settings.inference_key_file)
        self.calls = 0
        if type(output_token_limit) is not int or output_token_limit not in (1024, 4096):
            raise ProviderFailure("PROVIDER_OUTPUT_PROFILE_INVALID")
        self.output_token_limit = output_token_limit

    def complete(
        self, messages: list[dict], *, deadline: float | None = None,
        checkpoint=None, **options: object,
    ) -> tuple[dict, dict]:
        allowed_options = {
            "max_tokens",
            "response_format",
            "tools",
            "tool_choice",
            "reasoning_effort",
            "temperature",
        }
        cap = options.get("max_tokens", self.output_token_limit)
        if (
            set(options) - allowed_options
            or type(cap) is not int
            or not 1 <= cap <= self.output_token_limit
        ):
            raise ProviderFailure("PROVIDER_OPTIONS_INVALID")
        if deadline is not None and (
            type(deadline) not in (int, float) or not math.isfinite(deadline)
        ):
            raise ProviderFailure("PROVIDER_DEADLINE_INVALID")
        # The deadline belongs to the entire extraction, including repairs. HTTP read
        # timeouts alone do not bound a server that continually trickles response bytes.
        deadline = min(deadline, time.monotonic() + 60) if deadline is not None else (
            time.monotonic() + 60
        )
        self.check(deadline, checkpoint)
        if self.calls >= 3:
            raise ProviderFailure("CAPABILITY_CALL_LIMIT")
        self.calls += 1
        body = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": self.output_token_limit,
            **options,
        }
        started = time.monotonic()
        try:
            content = asyncio.run(self.request(body, deadline, checkpoint))
        except httpx.HTTPError:
            raise ProviderFailure("PROVIDER_UNAVAILABLE") from None
        self.check(deadline, None)
        try:
            payload = json.loads(content)
            choice = payload["choices"][0]
            if not isinstance(choice, dict):
                raise ProviderFailure("PROVIDER_SCHEMA_INVALID")
            message = choice["message"]
            usage = payload["usage"]
            if not isinstance(message, dict) or not isinstance(usage, dict):
                raise ProviderFailure("PROVIDER_SCHEMA_INVALID")
            counts = {
                key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            if (any(type(value) is not int or value < 0 for value in counts.values())
                    or counts["completion_tokens"] > cap
                    or counts["total_tokens"] != (
                        counts["prompt_tokens"] + counts["completion_tokens"])):
                raise ProviderFailure("PROVIDER_USAGE_INVALID")
            metadata = {
                "model": self.model_id,
                "usage": counts,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
            if choice.get("finish_reason", "stop") == "length":
                if message.get("content") is not None and not isinstance(message["content"], str):
                    raise ProviderFailure("PROVIDER_SCHEMA_INVALID")
                raise ProviderIncomplete(message, metadata)
            if choice.get("finish_reason", "stop") != "stop":
                raise ProviderFailure("PROVIDER_INCOMPLETE_RESPONSE")
            return message, metadata
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderFailure("PROVIDER_SCHEMA_INVALID") from None

    @staticmethod
    def check(deadline, checkpoint):
        if time.monotonic() >= deadline:
            raise ProviderFailure("INFERENCE_DEADLINE_EXPIRED")
        if checkpoint is not None:
            checkpoint()
        if time.monotonic() >= deadline:
            raise ProviderFailure("INFERENCE_DEADLINE_EXPIRED")

    async def request(self, body, deadline, checkpoint):
        async with httpx.AsyncClient(
            timeout=60, follow_redirects=False, trust_env=False,
        ) as client:
            async def receive():
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=body,
                ) as response:
                    if response.status_code != 200:
                        raise ProviderFailure(f"PROVIDER_HTTP_{response.status_code}")
                    content = bytearray()
                    checked_at = time.monotonic()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 1_048_576:
                            raise ProviderFailure("PROVIDER_RESPONSE_TOO_LARGE")
                        # Even a continuously readable stream cannot exceed wall time.
                        if time.monotonic() >= deadline:
                            raise ProviderFailure("INFERENCE_DEADLINE_EXPIRED")
                        if time.monotonic() - checked_at >= 5:
                            self.check(deadline, checkpoint)
                            checked_at = time.monotonic()
                            await asyncio.sleep(0)
                    return content

            operation = asyncio.create_task(receive())
            try:
                while True:
                    done, _ = await asyncio.wait(
                        {operation}, timeout=max(0, min(5, deadline - time.monotonic())),
                    )
                    self.check(deadline, checkpoint)
                    if done:
                        return operation.result()
            finally:
                # Close the in-flight HTTP request before returning to fenced cleanup.
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
