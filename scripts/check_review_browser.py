"""Real browser/HTTPS/Neon checks on freshly captured supplier evidence.

Called by check_evidence --browser-review after the actual worker and Vultr calls.
Isolated test worksheet constraints and automated decisions are not human acceptance.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from services.storage import jobs
from services.storage.database import database

ROOT = Path(__file__).resolve().parents[1]


def check_browser(settings, request_id, password):
    if not settings.database_schema.startswith("latch_test_"):
        raise ValueError("Browser verification requires an isolated schema")
    expect.set_options(timeout=60000)
    run = ROOT / "var/review-browser"
    run.mkdir(parents=True, exist_ok=True, mode=0o700)
    recovery = run / "active.json"
    recovery.write_text(json.dumps({"schema": settings.database_schema, "phase": "server"}))
    process = None
    origin = "https://localhost:8444"
    cert, key = run / "local.crt", run / "local.key"
    results, accessibility, errors = [], [], []
    try:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
        key.chmod(0o600)
        with (run / "server.log").open("a") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "services.api.app:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8444",
                    "--ssl-keyfile",
                    str(key),
                    "--ssl-certfile",
                    str(cert),
                    "--no-access-log",
                ],
                env={
                    **os.environ,
                    "LATCH_DB_SCHEMA": settings.database_schema,
                    "LATCH_EVIDENCE_DIR": str(settings.evidence_dir.resolve()),
                    "LATCH_PUBLIC_ORIGIN": origin,
                },
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        recovery.write_text(json.dumps({"schema": settings.database_schema, "pid": process.pid}))
        with httpx.Client(verify=False, timeout=3) as http:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("Review HTTPS server exited; inspect private log")
                try:
                    if http.get(origin + "/health/live").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("Review HTTPS server unavailable")
        print("Review browser HTTPS ready; real supplier evidence in isolated Neon.", flush=True)
        checkpoint = run / "phases.json"
        previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        resume = previous.get("schema") == settings.database_schema and previous.get("core_passed")
        if resume:
            results, accessibility = previous["layouts"], previous["axe"]
        with database(settings.database_url(), schema=settings.database_schema) as conn:
            conn.execute("UPDATE source_profiles SET active=true")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(
                ignore_https_errors=True, viewport={"width": 1440, "height": 1000}
            )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_default_timeout(60000)
            evidence_url = f"{origin}/requests/{request_id}/evidence"
            page.goto(evidence_url)
            page.get_by_label("Username", exact=True).fill("evidence_research")
            page.get_by_label("Password", exact=True).fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(
                page.get_by_role("heading", name="Supplier evidence UI assertion")
            ).to_be_visible()
            expect(page.locator(".review-summary")).to_contain_text("terms checked")
            price = page.get_by_role("button", name=re.compile("Price per selling pack"))
            panel = page.locator(".evidence-panel")
            if not resume:
                capture_response = page.request.get(
                    f"{origin}/api/v1/requests/{request_id}/evidence?version=1"
                ).json()["data"][0]
                extraction_id = capture_response["extraction_id"]
                initial = page.request.get(
                    f"{origin}/api/v1/extractions/{extraction_id}/review"
                ).json()["data"]
                supported_field = next(
                    f
                    for f in capture_response["extraction"]["fields"]
                    if f["state"] == "supported" and f["kind"] != "price_cents"
                )
                supported_kind = supported_field["kind"]
                baseline = sum(
                    f["state"] == "buyer_checked"
                    and f["original"]["kind"] not in ("price_cents", supported_kind)
                    for f in initial["fields"]
                )
                supported_checked = int(
                    any(
                        f["state"] == "buyer_checked" and f["original"]["kind"] == supported_kind
                        for f in initial["fields"]
                    )
                )
                history_count = 0
                with database(settings.database_url(), schema=settings.database_schema) as conn:
                    history_count = conn.execute(
                        "SELECT count(*) AS n FROM field_reviews"
                    ).fetchone()["n"]
                assert page.locator(".capture-image-scroll img").count() == 0
                price = page.get_by_role("button", name=re.compile("Price per selling pack"))
                price.click()
                panel = page.locator(".evidence-panel")
                expect(panel.get_by_text("Conflicting source values", exact=False)).to_be_visible()
                expect(
                    panel.get_by_role("button", name="Check this term", exact=True)
                ).to_be_disabled()
                expect(panel.locator("mark").first).to_be_visible()
                panel.get_by_role("button", name="Load screenshot", exact=True).click()
                expect(panel.locator("img")).to_be_visible()
                for _ in range(120):
                    if panel.locator("img").evaluate("el => el.complete && el.naturalWidth > 0"):
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Actual protected screenshot did not load")
                panel.get_by_label("Screenshot zoom", exact=True).select_option("double")
                assert panel.locator("img").evaluate("el => el.width") > 1440
                panel.get_by_label("Screenshot zoom", exact=True).select_option("fit")
                page.screenshot(path=str(run / "review-light-desktop.png"), full_page=True)
                panel.get_by_label("Corrected value", exact=True).fill("142.00")
                panel.get_by_label("Reason", exact=True).fill(
                    "Automated browser assertion selecting the captured surcharge amount"
                )
                panel.get_by_role("button", name="Save this decision", exact=True).click()
                expect(panel.get_by_role("alert")).to_contain_text("Acknowledge viewing")
                panel.get_by_label("I viewed the captured evidence for this term.").check()
                panel.get_by_label("Exact quote 1", exact=True).fill("Absent passage assertion")
                panel.get_by_role("button", name="Save this decision", exact=True).click()
                expect(panel.get_by_role("alert")).to_contain_text("one unique passage")
                # Restore the exact original quote directly from the protected capture API.
                evidence = page.request.get(
                    f"{origin}/api/v1/requests/{request_id}/evidence?version=1"
                ).json()["data"][0]
                price_field = next(
                    f for f in evidence["extraction"]["fields"] if f["kind"] == "price_cents"
                )
                panel.get_by_label("Exact quote 1", exact=True).fill(
                    price_field["spans"][0]["quote"]
                )
                panel.get_by_role("button", name="Save this decision", exact=True).click()
                expect(page.locator(".evidence-panel")).to_have_count(0)
                expect(
                    page.get_by_text(
                        f"{baseline + supported_checked + 1} of 10 terms checked", exact=True
                    )
                ).to_be_visible()
                expect(price).to_contain_text("$142.00")
                expect(price).to_be_focused()
                page.reload()
                expect(price).to_contain_text("$142.00")
                second = context.new_page()
                second.set_default_timeout(60000)
                second.goto(evidence_url)
                second.get_by_role("button", name=re.compile("Price per selling pack")).click()
                second_panel = second.locator(".evidence-panel")
                second_panel.get_by_role("button", name="Mark unclear", exact=True).click()
                second_panel.get_by_label("Reason", exact=True).fill(
                    "Automated stale tab assertion"
                )
                second_panel.get_by_label("I viewed the captured evidence for this term.").check()
                price.click()
                expect(panel.get_by_text("Conflicting source values", exact=False)).to_be_visible()
                expect(
                    panel.get_by_text(
                        "Automated browser assertion selecting the captured surcharge amount",
                        exact=True,
                    )
                ).to_be_visible()
                panel.get_by_role("button", name="Mark unclear", exact=True).click()
                panel.get_by_label("Reason", exact=True).fill(
                    "Automated browser assertion: purchase basis unresolved"
                )
                panel.get_by_label("I viewed the captured evidence for this term.").check()
                panel.get_by_role("button", name="Save this decision", exact=True).click()
                expect(
                    page.get_by_text(
                        f"{baseline + supported_checked} of 10 terms checked", exact=True
                    )
                ).to_be_visible()
                stale_submit = second_panel.get_by_role(
                    "button", name="Save this decision", exact=True
                )
                if stale_submit.is_enabled():
                    stale_submit.click()
                expect(
                    second_panel.get_by_text("The review or request changed.", exact=False)
                ).to_be_visible()
                expect(
                    second_panel.get_by_role("button", name="Save this decision", exact=True)
                ).to_be_disabled()
                second_panel.get_by_role("button", name="Load latest review", exact=True).click()
                expect(
                    second_panel.get_by_role("button", name="Save this decision", exact=True)
                ).to_be_enabled()
                expect(
                    second_panel.get_by_label("I viewed the captured evidence for this term.")
                ).not_to_be_checked()
                second.close()
                # Check a supported original individually, retaining the ambiguous price.
                catalog = json.loads((ROOT / "COPY.json").read_text())
                field = page.get_by_role(
                    "button", name=re.compile(re.escape(catalog[f"review.field.{supported_kind}"]))
                )
                field.click()
                panel.get_by_label("I viewed the captured evidence for this term.").check()
                panel.get_by_role("button", name="Save this decision", exact=True).click()
                expect(
                    page.get_by_text(f"{baseline + 1} of 10 terms checked", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Review history", exact=True).click()
                expect(page.locator(".history-record")).to_have_count(history_count + 3)
                expect(page.locator(".review-summary")).to_contain_text("Not confirmed")
                print(
                    "Browser review, persistence, exact quotes and stale tab passed.",
                    flush=True,
                )
                axe = (ROOT / "node_modules/axe-core/axe.min.js").read_text()
                for theme in ("light", "dark"):
                    # Use the actual application settings rather than injecting theme state.
                    page.get_by_role("link", name="Settings", exact=True).click()
                    page.get_by_role("button", name=theme.title(), exact=True).click()
                    page.goto(evidence_url)
                    expect(price).to_be_visible()
                    for width in (320, 390, 768, 1024, 1440, 1920):
                        page.set_viewport_size({"width": width, "height": 1000})
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        ), f"Ledger overflow {width}/{theme}"
                        price.click()
                        expect(
                            panel.get_by_role("heading", name="Price per selling pack", exact=True)
                        ).to_be_visible()
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        ), f"Evidence overflow {width}/{theme}"
                        if width < 1024:
                            assert panel.evaluate("el => el.matches(':modal')"), (
                                "Mobile evidence must be modal"
                            )
                            panel.get_by_role(
                                "button", name="Back to comparison", exact=True
                            ).focus()
                            page.keyboard.press("Shift+Tab")
                            assert panel.evaluate("el => el.contains(document.activeElement)"), (
                                "Mobile focus escaped evidence"
                            )
                        if width in (320, 1440):
                            page.evaluate(axe)
                            failures = page.evaluate("""async () => (await axe.run(document, {
                              runOnly: {type: 'tag',
                        values: ['wcag2a','wcag2aa','wcag21aa','wcag22aa']}
                            })).violations.map(v => ({id:v.id,
                        targets:v.nodes.map(n => n.target)}))""")
                            assert not failures, f"Review accessibility failures: {failures}"
                            accessibility.append(f"{width}/{theme}")
                        if width in (390, 1440):
                            page.screenshot(
                                path=str(run / f"review-{theme}-{width}.png"), full_page=True
                            )
                        page.keyboard.press("Escape")
                        # Desktop evidence is an inline nonmodal document; its Back control closes.
                        if width >= 1024:
                            panel.get_by_role(
                                "button", name="Back to comparison", exact=True
                            ).click()
                        expect(page.locator(".evidence-panel")).to_have_count(0)
                        expect(price).to_be_focused()
                        results.append(f"{width}/{theme}")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.emulate_media(reduced_motion="reduce")
                page.evaluate("document.body.style.zoom='2'")
                price.click()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    "200% review overflow"
                )
                assert (
                    panel.get_by_role("button", name="Save this decision", exact=True).evaluate(
                        "el => getComputedStyle(el).transitionDuration"
                    )
                    == "0s"
                )
                panel.get_by_role("button", name="Back to comparison", exact=True).click()
                page.evaluate("document.body.style.zoom='1'")
                assert not errors, "Browser runtime errors before core checkpoint"
                checkpoint.write_text(
                    json.dumps(
                        {
                            "schema": settings.database_schema,
                            "core_passed": True,
                            "layouts": results,
                            "axe": accessibility,
                            "zoom_200": True,
                        }
                    )
                )
            # Read eligibility from the API for actual expired/inactive profiles and jobs.
            with database(settings.database_url(), schema=settings.database_schema) as conn:
                owner = conn.execute(
                    "SELECT owner_id FROM requests WHERE id=%s", (request_id,)
                ).fetchone()["owner_id"]
                conn.execute("UPDATE source_profiles SET active=false")
            page.reload()
            price.click()
            expect(
                panel.get_by_role("button", name="Save this decision", exact=True)
            ).to_be_disabled()
            expect(
                panel.get_by_text("This supplier profile is unavailable", exact=False)
            ).to_be_visible()
            panel.get_by_role("button", name="Back to comparison", exact=True).click()
            # Expiry is immutable. Do not rewrite it to simulate the passage of time.
            with database(settings.database_url(), schema=settings.database_schema) as conn:
                conn.execute("UPDATE source_profiles SET active=true")
                queued = jobs.enqueue(conn, owner, request_id, 1, "ui_active_inspection")
            page.reload()
            price.click()
            expect(
                panel.get_by_role("button", name="Save this decision", exact=True)
            ).to_be_disabled()
            expect(
                panel.get_by_text("A source inspection is in progress", exact=False)
            ).to_be_visible()
            panel.get_by_role("button", name="Back to comparison", exact=True).click()
            with database(settings.database_url(), schema=settings.database_schema) as conn:
                jobs.cancel(conn, owner, queued["id"])
            page.reload()
            page.set_viewport_size({"width": 390, "height": 1000})
            price.click()
            expect(
                panel.get_by_role("heading", name="Price per selling pack", exact=True)
            ).to_be_visible()
            page.screenshot(path=str(run / "final-mobile-viewport.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.screenshot(path=str(run / "final-desktop-viewport.png"))
            panel.get_by_role("button", name="Back to comparison", exact=True).click()
            # Archive the isolated assertion and verify historical read-only review.
            with database(settings.database_url(), schema=settings.database_schema) as conn:
                conn.execute("UPDATE requests SET archived_at=1 WHERE id=%s", (request_id,))
            page.reload()
            price.click()
            expect(
                panel.get_by_role("button", name="Save this decision", exact=True)
            ).to_be_disabled()
            expect(
                panel.get_by_text("This source packet is not available", exact=False)
            ).to_be_visible()
            assert not errors, "Browser runtime errors; inspect private artifacts"
            context.close()
            browser.close()
        report = {
            "status": "passed",
            "at": datetime.now(UTC).isoformat(),
            "scope": "automated actual supplier evidence/browser/HTTPS/isolated Neon assertions",
            "observed_human_review": False,
            "buyer_acceptance": False,
            "layouts": results,
            "axe": accessibility,
            "zoom_200": True,
            "focus_restoration": True,
            "stale_tab_denied": True,
            "individual_check_correct_dispute": True,
            "immutable_original_history": True,
            "archived_read_only": True,
            "inactive_profile_and_active_inspection_blocked": True,
            "profile_time_expiry_observation": "not performed",
            "unknown_total_preserved": True,
        }
        (run / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        recovery.unlink(missing_ok=True)
