#!/usr/bin/env python3
"""Source-only actual public supplier research, with no buyer request or purchase acceptance."""

import argparse
import base64
import json
import time
from pathlib import Path
from uuid import uuid4

from services.common.config import Settings
from services.common.task_contracts import TaskCommand, TaskRef
from services.domain.contracts import RequestItem
from services.domain.extraction import unreviewed_offer
from services.runner.extraction import extract
from services.runner.supervisor import SupervisorClient
from services.runner.vultr import ProviderFailure, VultrClient

DIRECTORY = Path("var/supplier-extraction")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-only", action="store_true")
    parser.add_argument("--extract-existing", action="store_true")
    args = parser.parse_args()
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    target = DIRECTORY / "ubiquiti.capture"
    client = SupervisorClient(Path("private/supervisor-tls"))
    task = TaskCommand(
        task_id=uuid4(),
        job_id=uuid4(),
        fence=uuid4(),
        profile_id="ubiquiti_u6plus_research",
        profile_version=1,
        url="https://store.ui.com/us/en/products/u6-plus",
    )
    ref = TaskRef(job_id=task.job_id, fence=task.fence)
    try:
        if not args.extract_existing:
            (DIRECTORY / "active.json").write_text(task.model_dump_json())
            client.submit(task)
            start, ping = time.monotonic(), 0.0
            while time.monotonic() - start < 95:
                status = client.action(task.task_id, ref, "status")
                if status["cleanup_confirmed"]:
                    break
                if time.monotonic() - ping > 8:
                    client.action(task.task_id, ref, "heartbeat")
                    ping = time.monotonic()
                time.sleep(0.5)
            if status["state"] != "succeeded" or not status["cleanup_confirmed"]:
                (DIRECTORY / "capture-result.json").write_text(json.dumps(status, indent=2) + "\n")
                raise ValueError("Actual public supplier capture was unsupported")
            client.artifact(task.task_id, ref, target, status["artifact_hash"])
            capture = json.loads(target.read_bytes())
            (DIRECTORY / "ubiquiti.png").write_bytes(
                base64.b64decode(capture["png_base64"], validate=True)
            )
            (DIRECTORY / "active.json").unlink()
            print(
                "Actual public Ubiquiti product page captured and exact container removed.",
                flush=True,
            )
        if args.capture_only:
            return
        settings = Settings(
            model_id="qwen3.8-flash-next", inference_key_file=Path("private/vultr-inference-key")
        )
        # Public product identification for research only; no private buyer requirement is created.
        item = RequestItem(
            key="u6_plus",
            specification="Ubiquiti Access Point U6 Plus",
            public_specification="Ubiquiti Access Point U6 Plus",
            required_units=1,
        )
        result, usage = extract(
            VultrClient(settings, output_token_limit=4096),
            target.read_bytes(),
            source_id=uuid4(),
            items=[item],
            expected_pages=[{"url": task.url, "selector": "main"}],
            on_invalid=lambda value: (
                DIRECTORY / f"provider-attempt-{value['attempt']}.json"
            ).write_text(json.dumps(value, indent=2) + "\n"),
        )
        (DIRECTORY / "extraction.json").write_text(result.model_dump_json(indent=2) + "\n")
        offer = unreviewed_offer(result)
        report = {
            "scope": "actual_public_supplier_source_research",
            "status": "proposal_validated",
            "supplier_acceptance": "pending",
            "buyer_task": "not_created",
            "human_reviewed": False,
            "capture_hash": result.capture_hash,
            "proposal_hash": result.proposal_hash,
            "price_state": next(f.state for f in result.fields if f.kind == "price_cents"),
            "price_cents": offer.lines[0].price_cents,
            "shipping_cents": offer.shipping_cents,
            "tax_included": offer.tax_included,
            "latest_arrival": str(offer.latest_arrival) if offer.latest_arrival else None,
            "usage": usage,
        }
        (DIRECTORY / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
    except ProviderFailure as error:
        print(
            json.dumps(
                {
                    "scope": "actual_public_supplier_source_research",
                    "status": "unsupported",
                    "code": str(error),
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
    finally:
        if not args.extract_existing:
            client.revoke(ref)
        client.close()


if __name__ == "__main__":
    main()
