#!/usr/bin/env python3
"""Fresh public Vultr browser path. Records actual automation, never buyer acceptance."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "var/submission/public-demo"


def main():
    os.umask(0o077)
    RUN.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = json.loads((ROOT / "private/vultr-control-setup.json").read_text())
    origin = "https://" + state["hostname"]
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            record_video_dir=str(RUN),
            record_video_size={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.set_default_timeout(60000)
        page.goto(origin, wait_until="networkidle")
        page.screenshot(path=str(RUN / "home.png"), full_page=True)
        page.get_by_role("link", name="Open Latch").first.click()
        page.get_by_role("button", name="Try a private demo").click()
        page.get_by_role("button", name="Start the U6+ source demonstration").click()
        page.wait_for_url("**/requests/*")
        rid = page.url.rsplit("/", 1)[1]
        (RUN / "active.json").write_text(
            json.dumps({"origin": origin, "request_id": rid, "phase": "awaiting inspection"})
        )
        page.get_by_label(
            "I have checked the public descriptions and agree to capture and inference."
        ).check()
        page.get_by_role("button", name="Inspect offers", exact=True).click()
        page.get_by_text("Evidence ready for review", exact=True).wait_for(timeout=240000)
        page.screenshot(path=str(RUN / "inspected.png"), full_page=True)
        (RUN / "active.json").write_text(
            json.dumps({"origin": origin, "request_id": rid, "phase": "review"})
        )
        page.goto(origin + f"/requests/{rid}/evidence", wait_until="networkidle")
        page.locator(".term-row").first.wait_for(state="visible")
        page.locator(".image-correspondence summary").click()
        page.locator(".term-row").first.click()
        page.get_by_role("button", name="Load screenshot", exact=True).click()
        page.locator(".capture-image-scroll img").wait_for(state="visible")
        page.screenshot(path=str(RUN / "review.png"), full_page=True)
        actual = page.request.get(origin + f"/api/v1/requests/{rid}/evidence")
        assert actual.status == 200
        assert len(actual.json()["data"]) == 1
        for captured in actual.json()["data"]:
            for artifact in captured["pages"]:
                response = page.request.get(origin + f'/api/v1/artifacts/{artifact["artifact_id"]}')
                assert response.status == 200
                assert hashlib.sha256(response.body()).hexdigest() == artifact["sanitized_hash"]
        # Persist public-source evidence and status only, never cookies or session bodies.
        (RUN / "captures.json").write_text(actual.text())
        page.goto(origin + f"/requests/{rid}/compare", wait_until="networkidle")
        page.locator(".decision-tools").wait_for(state="visible")
        page.get_by_role("button", name="Save current comparison", exact=True).click()
        page.locator(".comparison-totals").first.wait_for(state="visible")
        page.screenshot(path=str(RUN / "comparison.png"), full_page=True)
        page.goto(origin + f"/requests/{rid}", wait_until="networkidle")
        page.get_by_label("Public supplier page", exact=True).fill(
            "https://169.254.169.254/latest/meta-data/"
        )
        page.get_by_role("button", name="Save draft", exact=True).click()
        page.locator(".field-error").first.wait_for(state="visible")
        page.screenshot(path=str(RUN / "containment.png"), full_page=True)
        page.reload(wait_until="networkidle")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(RUN / "mobile.png"), full_page=True)
        overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        video = page.video
        context.close()
        video.save_as(str(RUN / "demo.webm"))
        browser.close()
    result = {
        "status": "passed",
        "at": datetime.now(UTC).isoformat(),
        "public_origin": origin,
        "request_id": rid,
        "scope": "actual public Vultr browser automation and fresh supplier inspection",
        "buyer_acceptance": False,
        "approved": False,
        "released": False,
        "mobile_overflow": overflow,
        "page_errors": errors,
    }
    (RUN / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert not overflow and not errors, result
    (RUN / "active.json").unlink()
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
