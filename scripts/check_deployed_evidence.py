#!/usr/bin/env python3
"""Actual public owner/artifact verification on the recorded demonstration, without inference."""

import hashlib
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from services.api.auth import COOKIE, new_session, token_hash
from services.api.settings import AppSettings
from services.storage.database import database

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "var/submission/public-demo"


def main():
    os.umask(0o077)
    result = json.loads((RUN / "result.json").read_text())
    origin = result["public_origin"]
    rid = result["request_id"]
    settings = AppSettings.from_environment()
    with database(settings.database_url()) as c:
        owner = c.execute("SELECT owner_id FROM requests WHERE id=%s", (rid,)).fetchone()[
            "owner_id"
        ]
        token = new_session(c, owner)
        c.execute(
            "UPDATE sessions SET reauthenticated_at=0 WHERE token_hash=%s", (token_hash(token),)
        )
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.add_cookies(
                [
                    {
                        "name": COOKIE,
                        "value": token,
                        "url": origin,
                        "secure": True,
                        "httpOnly": True,
                        "sameSite": "Lax",
                    }
                ]
            )
            page = context.new_page()
            page.set_default_timeout(60000)
            page.goto(origin + f"/requests/{rid}", wait_until="networkidle")
            for theme in ["light", "dark"]:
                page.evaluate(
                    '(theme) => {localStorage.setItem("latch-theme",theme);'
                    "document.documentElement.dataset.theme=theme}",
                    theme,
                )
                page.set_viewport_size({"width": 390, "height": 844})
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
                page.screenshot(path=str(RUN / f"final-mobile-{theme}.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            response = page.request.get(origin + f"/api/v1/requests/{rid}/evidence")
            assert response.status == 200
            captures = response.json()["data"]
            assert len(captures) == 1
            hashes = []
            for capture in captures:
                for artifact in capture["pages"]:
                    response = page.request.get(
                        origin + f"/api/v1/artifacts/{artifact['artifact_id']}"
                    )
                    assert response.status == 200
                    assert response.headers["content-type"].startswith("image/png")
                    digest = hashlib.sha256(response.body()).hexdigest()
                    assert digest == artifact["sanitized_hash"]
                    hashes.append(digest)
            page.goto(origin + f"/requests/{rid}/evidence", wait_until="networkidle")
            page.locator(".term-row").first.click()
            page.get_by_role("button", name="Load screenshot", exact=True).click()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if page.evaluate(
                    '() => {const img=document.querySelector(".capture-image-scroll img");'
                    'return img?.complete && img?.naturalWidth > 0}'
                ):
                    break
                page.wait_for_timeout(250)
            else:
                raise AssertionError("Captured image did not load")
            with browser.new_context() as other:
                foreign = other.request.post(
                    origin + "/api/v1/auth/demo",
                    data={},
                    headers={"Origin": origin, "Content-Type": "application/json"},
                )
                assert foreign.status == 200
                assert other.request.get(origin + f"/api/v1/requests/{rid}/evidence").status == 404
                assert (
                    other.request.get(
                        origin + f"/api/v1/artifacts/{captures[0]['pages'][0]['artifact_id']}"
                    ).status
                    == 404
                )
            page.evaluate((ROOT / "node_modules/axe-core/axe.min.js").read_text())
            accessibility = page.evaluate(
                'async () => (await axe.run(document,{runOnly:{type:"tag",'
                'values:["wcag2a","wcag2aa"]}})).violations.map(v => '
                "({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)}))"
            )
            assert not accessibility, accessibility
            context.close()
            browser.close()
        (RUN / "security-result.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "artifact_hashes": hashes,
                    "other_owner_denied": True,
                    "loaded_image": True,
                    "mobile_themes": 2,
                    "axe_violations": accessibility,
                },
                indent=2,
            )
            + "\n"
        )
        print("Artifact hashes, image loading, owner denial, mobile themes and axe passed.")
    finally:
        with database(settings.database_url()) as c:
            c.execute(
                "UPDATE sessions SET revoked_at=floor(extract(epoch FROM clock_timestamp())*1000)"
                "::bigint WHERE token_hash=%s",
                (token_hash(token),),
            )


if __name__ == "__main__":
    main()
