#!/usr/bin/env python3
"""Actual Vultr image input on the worker's technical capture, separate from supplier acceptance."""

import base64
import hashlib
import json
from pathlib import Path

from services.common.config import Settings
from services.common.preflight import require_json_object, write_report
from services.runner.vultr import VultrClient


def main():
    capture = json.loads(Path("var/documentation-capture.json").read_text())
    png = base64.b64decode(capture["png_base64"], validate=True)
    if (capture.get("url") != "https://gvisor.dev/docs/" or capture.get("uid") != 1000
            or capture.get("complete") is not True or len(png) > 10 * 1024 * 1024
            or not png.startswith(b"\x89PNG\r\n\x1a\n")
            or hashlib.sha256(png).hexdigest() != capture["png_sha256"]):
        raise ValueError("Actual documentation capture required")
    settings = Settings(model_id="qwen3.8-flash-next",
                        inference_key_file=Path("private/vultr-inference-key"))
    message, usage = VultrClient(settings).complete([
        {"role": "user", "content": [
            {"type": "text", "text": (
                "Read this actual public technical documentation capture. Return JSON with only "
                "visible_text (a short transcription of the first readable paragraph) and "
                "uncertain (a boolean). Abstain if illegible."
            )},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + capture["png_base64"]
            }},
        ]},
    ], response_format={"type": "json_object"}, reasoning_effort="minimal")
    value = require_json_object(message, {"visible_text", "uncertain"})
    if (not isinstance(value["visible_text"], str) or not value["visible_text"].strip()
            or value["uncertain"] is not False):
        raise ValueError("Actual image capability abstained")
    report = {"status": "passed", "scope": "live_vultr_documentation_image_input",
              "capture_sha256": capture["png_sha256"], "vision": usage,
              "proposal": value, "supplier_accuracy_and_buyer_acceptance": "pending"}
    write_report(settings, "infrastructure_vision", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
