#!/usr/bin/env python3
"""Provision/recover the authorized Latch inference subscription without printing credentials."""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from services.common.config import read_secret

PRIVATE = Path("private")
STATE = PRIVATE / "vultr-inference-state.json"
LABEL = "latch-inference"


def save(path: Path, value: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".inference-", dir=PRIVATE)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(value)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    if PRIVATE.is_symlink() or PRIVATE.stat().st_mode & 0o077:
        raise ValueError("Owned private operator directory required")
    state = {"label": LABEL, "at": datetime.now(UTC).isoformat()}
    with httpx.Client(
        base_url="https://api.vultr.com/v2",
        headers={"Authorization": "Bearer " + read_secret(PRIVATE / "vultr-api-key")},
        timeout=30,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = client.get("/inference")
        if response.status_code != 200:
            raise ValueError(f"INVENTORY_HTTP_{response.status_code}")
        matches = [row for row in response.json()["subscriptions"] if row["label"] == LABEL]
        if len(matches) > 1:
            raise ValueError("DUPLICATE_SUBSCRIPTION_REVIEW_REQUIRED")
        if not matches:
            state["operation"] = "create_subscription_started"
            save(STATE, json.dumps(state, indent=2) + "\n")
            # Never automatically retry a POST. A rerun inventories the provider first.
            response = client.post("/inference", json={"label": LABEL})
            if response.status_code != 201:
                state.update(operation="create_failed", http_status=response.status_code)
                save(STATE, json.dumps(state, indent=2) + "\n")
                raise ValueError(f"CREATE_HTTP_{response.status_code}")
            subscription = response.json()["subscription"]
        else:
            response = client.get("/inference/" + matches[0]["id"])
            if response.status_code != 200:
                raise ValueError(f"SUBSCRIPTION_HTTP_{response.status_code}")
            subscription = response.json()["subscription"]
        state.update(operation="subscription_found", subscription_id=subscription["id"])
        save(STATE, json.dumps(state, indent=2) + "\n")
        token = subscription.get("api_key")
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ValueError("INFERENCE_CREDENTIAL_NOT_RETURNED")
        save(PRIVATE / "vultr-inference-key", token + "\n")
        state["operation"] = "credential_saved"
        save(STATE, json.dumps(state, indent=2) + "\n")
    with httpx.Client(
        timeout=30, trust_env=False, follow_redirects=False,
        headers={"Authorization": "Bearer " + read_secret(PRIVATE / "vultr-inference-key")},
    ) as client:
        response = client.get("https://api.vultrinference.com/v1/models")
        if response.status_code != 200:
            raise ValueError(f"CATALOG_HTTP_{response.status_code}")
        if len(response.content) > 1024 * 1024:
            raise ValueError("CATALOG_TOO_LARGE")
        catalog = response.json()
        save(PRIVATE / "vultr-model-catalog.json", json.dumps(catalog, indent=2) + "\n")
        state["operation"] = "catalog_verified"
        save(STATE, json.dumps(state, indent=2) + "\n")
        print(json.dumps({
            "status": "catalog_verified",
            "subscription_id": state["subscription_id"],
            "model_ids": [row["id"] for row in catalog["data"]],
        }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, httpx.HTTPError) as error:
        # Exceptions/bodies may contain authentication or user input. Emit a class only.
        print(json.dumps({"status": "failed", "error_class": type(error).__name__}))
        raise SystemExit(1) from None
