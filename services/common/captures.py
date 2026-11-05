"""Bounded byte/hash validation for quarantined captures; no image decoding or network access."""

import base64
import hashlib
import json
from datetime import datetime


def capture_artifact(output: bytes, payload: dict) -> str:
    """Worker output is untrusted; validate the entire bounded capture before accepting it."""
    if len(output) > 15 * 1024 * 1024:
        raise ValueError("ARTIFACT_TOO_LARGE")
    value = json.loads(output)
    if value.get("complete") is not True or value.get("uid") != 1000:
        raise ValueError("CAPTURE_INCOMPLETE")
    pages = value.get("pages")
    if not isinstance(pages, list) or len(pages) != len(payload["pages"]):
        raise ValueError("CAPTURE_PAGE_SET")
    total = 0
    for index, (page, target) in enumerate(zip(pages, payload["pages"], strict=True)):
        if page["url"] != target["url"] or page["observed_urls"] != [target["url"]]:
            raise ValueError("CAPTURE_URL_CHAIN")
        if page["status"] != 200:
            raise ValueError("CAPTURE_STATUS")
        text = page["text"].encode()
        png = base64.b64decode(
            value["png_base64"] if index == 0 else page["png_base64"], validate=True
        )
        total += len(text) + len(png)
        if not text.strip() or len(text) > 32768 or total > 10 * 1024 * 1024:
            raise ValueError("CAPTURE_CONTENT_LIMIT")
        if len(png) < 33 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
            raise ValueError("CAPTURE_PNG")
        width, height = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
        if (
            type(page["width"]) is not int
            or type(page["height"]) is not int
            or ((page["width"], page["height"]) != (width, height))
            or not 1 <= width <= 4000
            or not 1 <= height <= 16000
        ):
            raise ValueError("CAPTURE_DIMENSIONS")
        for data, key in ((text, "text_sha256"), (png, "png_sha256")):
            if hashlib.sha256(data).hexdigest() != page[key]:
                raise ValueError("CAPTURE_HASH")
        start = datetime.fromisoformat(page["started_at"])
        end = datetime.fromisoformat(page["completed_at"])
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or not 0 <= (end - start).total_seconds() <= 90
        ):
            raise ValueError("CAPTURE_INTERVAL")
    return hashlib.sha256(output).hexdigest()
