"""Bounded Vultr capability client. This module has no purchasing authority."""

import json
import time

import httpx

from services.common.config import Settings, read_secret


class ProviderFailure(Exception):
    """A safe code, never a raw provider response or credential."""


class VultrClient:
    def __init__(self, settings: Settings):
        if not settings.model_id or settings.inference_key_file is None:
            raise ProviderFailure("INFERENCE_NOT_CONFIGURED")
        self.model_id = settings.model_id
        self.endpoint = settings.inference_base_url + "/chat/completions"
        self._key = read_secret(settings.inference_key_file)
        self.calls = 0

    def complete(self, messages: list[dict], **options: object) -> tuple[dict, dict]:
        if self.calls >= 3:
            raise ProviderFailure("CAPABILITY_CALL_LIMIT")
        self.calls += 1
        body = {
            "model": self.model_id,
            "messages": messages,
            "max_completion_tokens": 1024,
            **options,
        }
        started = time.monotonic()
        try:
            with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "POST",
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=body,
                ) as response:
                    if response.status_code != 200:
                        raise ProviderFailure(f"PROVIDER_HTTP_{response.status_code}")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 1_048_576:
                            raise ProviderFailure("PROVIDER_RESPONSE_TOO_LARGE")
            payload = json.loads(content)
            message = payload["choices"][0]["message"]
            usage = payload["usage"]
            if not isinstance(message, dict) or not isinstance(usage, dict):
                raise ProviderFailure("PROVIDER_SCHEMA_INVALID")
            counts = {
                key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            if any(type(value) is not int or value < 0 for value in counts.values()):
                raise ProviderFailure("PROVIDER_USAGE_INVALID")
            metadata = {
                "model": self.model_id,
                "usage": counts,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
            return message, metadata
        except httpx.HTTPError as exc:
            raise ProviderFailure("PROVIDER_UNAVAILABLE") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderFailure("PROVIDER_SCHEMA_INVALID") from exc
