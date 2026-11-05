"""Real browser → HTTPS API → isolated Neon schema → persisted worksheet checks.

These are local product checks with arithmetic/form assertions, not supplier or Vultr acceptance.
No network route interception, fake responses, production seed rows or source captures are used.
"""

import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from playwright.sync_api import expect, sync_playwright
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.api.auth import IDLE_MS, now_ms, provision_user  # noqa: E402
from services.api.settings import AppSettings  # noqa: E402
from services.storage.database import database, direct_url, initialize  # noqa: E402


def main() -> None:
    expect.set_options(timeout=60000)
    os.chdir(ROOT)
    settings = AppSettings.from_environment()
    url = settings.database_url()
    schema = "latch_test_" + uuid4().hex
    run = ROOT / "var/browser-check"
    run.mkdir(parents=True, exist_ok=True, mode=0o700)
    (run / "recovery.json").write_text(json.dumps({"schema": schema, "pid": None}))
    key, cert = run / "local.key", run / "local.crt"
    password = secrets.token_urlsafe(24)
    process = None

    def stop_server():
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)

    def start_server():
        nonlocal process
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
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        (run / "recovery.json").write_text(json.dumps({"schema": schema, "pid": process.pid}))
        with httpx.Client(verify=False, timeout=3) as http:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("HTTPS server exited; inspect private server.log")
                try:
                    if http.get("https://localhost:8444/health/live").status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
        raise RuntimeError("HTTPS server did not become ready")

    try:
        initialize(url, schema=schema)
        with database(url, schema=schema) as conn:
            provision_user(conn, "browser_assertion", "Browser assertion", password)
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
        env = {
            **os.environ,
            "LATCH_DB_SCHEMA": schema,
            "LATCH_PUBLIC_ORIGIN": "https://localhost:8444",
        }
        start_server()
        print("HTTPS server ready; isolated Neon schema active.", flush=True)
        with sync_playwright() as browser_tools:
            browser = browser_tools.chromium.launch()
            context = browser.new_context(
                ignore_https_errors=True, viewport={"width": 1440, "height": 1000}
            )
            page = context.new_page()
            page.set_default_timeout(60000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "response",
                lambda response: (
                    print(
                        "HTTP",
                        response.status,
                        response.url.split("localhost:8444")[-1],
                        flush=True,
                    )
                    if "/api/" in response.url
                    else None
                ),
            )
            page.on(
                "requestfailed",
                lambda request: print(
                    "REQUEST_FAILED", request.url.split("localhost:8444")[-1], flush=True
                ),
            )
            page.goto("https://localhost:8444")
            expect(
                page.get_by_role("heading", name="Make sure the whole kit is in the quote.")
            ).to_be_visible()
            page.get_by_role("link", name="Open Latch", exact=True).first.click()
            page.get_by_label("Username", exact=True).fill("browser_assertion")
            page.get_by_role("button", name="Show password", exact=True).click()
            expect(page.get_by_label("Password", exact=True)).to_have_attribute("type", "text")
            page.get_by_role("button", name="Hide password", exact=True).click()
            page.get_by_label("Password", exact=True).fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_role("heading", name="Your requests.")).to_be_visible()
            expect(page.get_by_role("heading", name="A little breathing room.")).to_be_visible()
            page.screenshot(path=str(run / "empty-light.png"), full_page=True)
            page.get_by_role("link", name="New request", exact=True).first.click()
            page.get_by_label("Request name", exact=True).fill("Browser persistence assertion")
            page.get_by_label("Budget", exact=False).fill("123.45")
            deadline = (
                (datetime.now(UTC) + timedelta(days=7))
                .replace(second=0, microsecond=0)
                .strftime("%Y-%m-%dT%H:%M")
            )
            page.get_by_label("Deadline timezone", exact=False).fill("UTC")
            page.get_by_label("Needed by", exact=True).fill(deadline)
            page.get_by_label("Delivery assumptions", exact=True).fill("Calendar deadline in UTC")
            page.get_by_label("Required specification", exact=True).fill(
                "Private worksheet boundary assertion"
            )
            page.get_by_label("Specification shared with suppliers", exact=True).fill(
                "Public worksheet boundary assertion"
            )
            page.get_by_label("Quantity", exact=True).fill("25")
            page.get_by_role("button", name="Save draft", exact=True).click()
            expect(page).to_have_url(re.compile(r"/requests/[a-f0-9-]{36}$"))
            expect(
                page.get_by_text("This version is stored. You can return to it later.", exact=True)
            ).to_be_visible()
            request_url = page.url
            stop_server()
            start_server()
            page.reload()
            expect(page.get_by_label("Budget", exact=False)).to_have_value("123.45")
            second = context.new_page()
            second.on("pageerror", lambda error: errors.append(str(error)))
            second.set_default_timeout(60000)
            second.goto(request_url)
            expect(second.get_by_label("Quantity", exact=True)).to_have_value("25")
            second.get_by_label("Request name", exact=True).fill("Revised browser assertion")
            second.get_by_role("button", name="Save draft", exact=True).click()
            expect(second.get_by_text("Your draft is saved.", exact=True)).to_be_visible()
            page.get_by_label("Request name", exact=True).fill("Conflicting browser assertion")
            page.get_by_role("button", name="Save draft", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text(
                "This request changed in another tab."
            )
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Load latest version", exact=True).click()
            expect(page.get_by_label("Request name", exact=True)).to_have_value(
                "Revised browser assertion"
            )
            expect(page.get_by_role("button", name="Inspect offers", exact=True)).to_be_disabled()
            print("Browser save/reload, another tab and version conflict passed.", flush=True)
            page.get_by_role("link", name="Version 1", exact=True).click()
            expect(page.get_by_label("Request name", exact=True)).to_have_value(
                "Browser persistence assertion"
            )
            expect(page.get_by_label("Request name", exact=True)).to_be_disabled()
            page.get_by_role("link", name="Current version", exact=True).click()
            expect(page.get_by_label("Request name", exact=True)).to_have_value(
                "Revised browser assertion"
            )
            page.get_by_role("link", name="Settings", exact=True).click()
            page.get_by_label("Password", exact=True).fill(password)
            page.get_by_role("button", name="Confirm your password", exact=True).click()
            expect(page.get_by_text("Your identity was confirmed.", exact=True)).to_be_visible()
            page.get_by_role("button", name="Dark", exact=True).click()
            page.goto(request_url)
            expect(page.get_by_role("link", name="Version 1", exact=True)).to_be_visible()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(run / "worksheet-dark-desktop.png"), full_page=True)
            page.get_by_role("link", name="Settings", exact=True).click()
            page.get_by_role("button", name="Light", exact=True).click()
            page.goto(request_url)
            expect(page.get_by_role("link", name="Version 1", exact=True)).to_be_visible()
            page.screenshot(path=str(run / "worksheet-light-desktop.png"), full_page=True)
            layouts = []
            accessibility = []
            axe = (ROOT / "node_modules/axe-core/axe.min.js").read_text()
            for theme in ("light", "dark"):
                page.get_by_role("link", name="Settings", exact=True).click()
                page.get_by_role("button", name=theme.title(), exact=True).click()
                page.goto(request_url)
                expect(page.get_by_role("link", name="Version 1", exact=True)).to_be_visible()
                for width in (320, 390, 768, 1024, 1440, 1920):
                    page.set_viewport_size({"width": width, "height": 1000})
                    expect(page.get_by_label("Request name", exact=True)).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        f"Overflow at {width}/{theme}"
                    )
                    layouts.append(f"{width}/{theme}")
                    expect(page.get_by_role("link", name="Settings", exact=True)).to_be_visible()
                    if width in (320, 1440):
                        page.evaluate(axe)
                        violations = page.evaluate("""async () => (await axe.run(document, {
                          runOnly: {type: 'tag',
                            values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}
                        })).violations.map(v => ({id: v.id,
                          targets: v.nodes.map(n => n.target)}))""")
                        assert not violations, f"Accessibility failures: {violations}"
                        accessibility.append(f"{width}/{theme}")
                    if width == 390:
                        page.screenshot(
                            path=str(run / f"worksheet-{theme}-mobile.png"), full_page=True
                        )
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.emulate_media(reduced_motion="reduce")
            assert (
                page.get_by_role("button", name="Inspect offers", exact=True).evaluate(
                    "el => getComputedStyle(el).transitionDuration"
                )
                == "0s"
            )
            page.evaluate("document.body.style.zoom='2'")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                "Overflow at 200 percent zoom"
            )
            page.evaluate("document.body.style.zoom='1'")
            page.get_by_label("Request name", exact=True).focus()
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.tagName") == "INPUT"
            assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "solid"
            assert not errors, "Browser runtime errors; inspect private evidence"
            # Validate actual server persistence directly, not a frontend flag.
            with database(url, schema=schema) as conn:
                assert (
                    conn.execute("SELECT count(*) AS n FROM request_versions").fetchone()["n"] == 2
                )
            second.close()
            decision_layouts = []
            for theme in ("light", "dark"):
                page.get_by_role("link", name="Settings", exact=True).click()
                page.get_by_role("button", name=theme.title(), exact=True).click()
                page.goto(request_url + "/compare")
                expect(page.get_by_role("heading", name="No comparison saved yet.")).to_be_visible()
                expect(
                    page.get_by_role("button", name="Approve this version", exact=True)
                ).to_be_disabled()
                for width in (320, 390, 768, 1024, 1440, 1920):
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    decision_layouts.append(f"{width}/{theme}")
                    if width in (320, 1440):
                        page.evaluate(axe)
                        violations = page.evaluate("""async () => (await axe.run(document, {
                            runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}
                        })).violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))""")
                        assert not violations, f"Decision accessibility failures: {violations}"
                    if width in (390, 1440):
                        page.screenshot(
                            path=str(run / f"decision-{theme}-{width}.png"), full_page=True
                        )
            page.get_by_role("button", name="Save current comparison", exact=True).click()
            expect(page.get_by_role("alert")).to_be_visible()
            expect(page.get_by_role("heading", name="No comparison saved yet.")).to_be_visible()
            page.goto(request_url)
            expect(page.get_by_role("link", name="Version 1", exact=True)).to_be_visible()
            page.get_by_role("link", name="Settings", exact=True).click()
            page.get_by_role("button", name="System", exact=True).click()
            page.goto(request_url)
            expect(page.get_by_role("link", name="Version 1", exact=True)).to_be_visible()
            for scheme in ("light", "dark"):
                page.emulate_media(color_scheme=scheme)
                expect(page.locator("html")).to_have_attribute("data-theme", scheme)
            page.get_by_role("button", name="Archive request", exact=True).click()
            expect(page.get_by_label("Request name", exact=True)).to_be_disabled()
            page.reload()
            expect(page.get_by_label("Request name", exact=True)).to_be_disabled()
            with database(url, schema=schema) as conn:
                assert conn.execute("SELECT archived_at FROM requests").fetchone()["archived_at"]
                conn.execute("UPDATE sessions SET last_seen_at=%s", (now_ms() - IDLE_MS,))
            page.reload()
            expect(page.get_by_role("heading", name="Welcome to Latch.")).to_be_visible()
            page.get_by_label("Username", exact=True).fill("browser_assertion")
            page.get_by_label("Password", exact=True).fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_label("Request name", exact=True)).to_be_disabled()
            page.get_by_role("button", name="Sign out", exact=True).click()
            expect(page.get_by_role("heading", name="Welcome to Latch.")).to_be_visible()
            context.close()
            browser.close()
            result = {
                "at": datetime.now(UTC).isoformat(),
                "status": "passed",
                "scope": "real HTTPS/browser/Neon saved worksheet assertions",
                "layouts": layouts,
                "save_reload_another_tab": True,
                "server_restart": True,
                "historical_version_readonly": True,
                "archive_reload": True,
                "session_expiry_reauth_logout": True,
                "version_conflict": True,
                "theme_persistence": True,
                "system_theme_changes": True,
                "axe_wcag22aa_layouts": accessibility,
                "keyboard_focus": True,
                "zoom_200_percent": True,
                "reduced_motion": True,
                "console_errors": len(errors),
                "decision_empty_and_no_authority": True,
                "decision_layouts": decision_layouts,
                "live_supplier_or_vultr_acceptance": False,
            }
            (run / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result), flush=True)
    finally:
        stop_server()
        with psycopg.connect(direct_url(url), connect_timeout=10) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        (run / "recovery.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
