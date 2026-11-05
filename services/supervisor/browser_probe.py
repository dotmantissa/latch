"""Fixed P0 program baked into a disposable image. No credentials or buyer context."""

import base64
import hashlib
import json
import os
import re
import socket
import sys
import time
import unicodedata
from datetime import UTC, datetime
from urllib.parse import urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import sync_playwright

MAX_BYTES = 10 * 1024 * 1024


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def capture_page(context, target: dict) -> dict:
    page = context.new_page()
    observed_urls = []
    page.on(
        "response",
        lambda response: (
            observed_urls.append(response.url) if response.request.is_navigation_request() else None
        ),
    )
    started = now()
    response = page.goto(target["url"], wait_until="domcontentloaded", timeout=20_000)
    if response is None or response.status != 200 or page.url != target["url"]:
        raise ValueError("SOURCE_RESPONSE_UNSUPPORTED")
    region = page.locator(target["selector"])
    if region.count() != 1:
        raise ValueError("SOURCE_REGION_AMBIGUOUS")
    region.wait_for(state="visible", timeout=20_000)
    bounds = region.bounding_box(timeout=5000)
    if bounds is None or not 1 <= bounds["width"] <= 4000 or not 1 <= bounds["height"] <= 16000:
        raise ValueError("SOURCE_REGION_EXCEEDS_LIMITS")
    text = unicodedata.normalize("NFC", region.inner_text(timeout=5000).replace("\r\n", "\n"))
    if not text.strip() or len(text.encode()) > 32 * 1024:
        raise ValueError("SOURCE_TEXT_INCOMPLETE_OR_TOO_LARGE")
    png = region.screenshot(type="png", timeout=20_000, animations="disabled")
    if len(png) + len(text.encode()) > MAX_BYTES:
        raise ValueError("SOURCE_ARTIFACT_TOO_LARGE")
    result = {
        "url": page.url,
        "status": response.status,
        "started_at": started,
        "completed_at": now(),
        "observed_urls": observed_urls,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "png_base64": base64.b64encode(png).decode(),
        "width": int.from_bytes(png[16:20], "big"),
        "height": int.from_bytes(png[20:24], "big"),
    }
    if result["width"] > 4000 or result["height"] > 16000:
        raise ValueError("SOURCE_RASTER_EXCEEDS_LIMITS")
    page.close()
    return result


def main() -> int:
    payload = json.loads(sys.stdin.buffer.read(256 * 1024 + 1))
    if set(payload) != {"mode", "pages", "asset_origins", "proxy"}:
        raise ValueError("TASK_SCHEMA_INVALID")
    if os.getuid() == 0:
        raise ValueError("NONROOT_REQUIRED")
    if payload["mode"] == "timeout":
        time.sleep(120)  # Fixed scoped watchdog probe; the host must terminate this task.
        raise ValueError("WATCHDOG_DID_NOT_TERMINATE_TASK")
    if payload["mode"] != "capture" or not 1 <= len(payload["pages"]) <= 2:
        raise ValueError("TASK_SCHEMA_INVALID")
    allowed_urls = {target["url"] for target in payload["pages"]}
    asset_origins = set(payload["asset_origins"])
    proxy_spki = os.environ.get("LATCH_PROXY_CA_SPKI", "")
    if not proxy_spki or len(base64.b64decode(proxy_spki, validate=True)) != 32:
        raise ValueError("PINNED_PROXY_CA_REQUIRED")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            channel="chromium",
            chromium_sandbox=True,
            proxy={"server": payload["proxy"]},
            args=[
                "--disable-quic",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--ignore-certificate-errors-spki-list=" + proxy_spki,
            ],
        )
        diagnostic = browser.new_page()
        diagnostic.goto("chrome://sandbox")
        sandbox_text = diagnostic.locator("body").inner_text()
        for required in ("PID namespaces\tYes", "Network namespaces\tYes",
                         "Seccomp-BPF sandbox\tYes"):
            if required not in sandbox_text:
                raise ValueError("CHROMIUM_SANDBOX_NOT_EFFECTIVE")
        diagnostic.close()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            accept_downloads=False,
            service_workers="block",
            java_script_enabled=True,
        )

        def bound_requests(route):
            request = route.request
            parsed = urlsplit(request.url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if request.is_navigation_request():
                permitted = request.url in allowed_urls
            else:
                permitted = origin in asset_origins and parsed.scheme == "https"
            if permitted and request.resource_type != "websocket":
                route.continue_()
            else:
                route.abort("blockedbyclient")

        context.route("**/*", bound_requests)
        context.route_web_socket("**/*", lambda websocket: websocket.close())
        pages = [capture_page(context, target) for target in payload["pages"]]
        total_bytes = sum(
            len(base64.b64decode(p["png_base64"])) + len(p["text"].encode()) for p in pages
        )
        if total_bytes > MAX_BYTES:
            raise ValueError("SOURCE_ARTIFACT_TOO_LARGE")
        # Remove browser interception for these fixed probes. Host/proxy must enforce denial.
        context.unroute("**/*", bound_requests)
        network_observations = {}
        probe_page = context.new_page()
        for name, url in {
            "metadata": "https://169.254.169.254/",
            "private": "https://10.0.0.1/",
            "loopback": "https://127.0.0.1/",
            "ipv6_private": "https://[fd00::1]/",
        }.items():
            try:
                probe_page.goto(url, wait_until="commit", timeout=4000)
                network_observations[name] = "response_observed"
            except BrowserError:
                network_observations[name] = "request_failed"
        try:
            with socket.create_connection(("8.8.8.8", 443), timeout=3):
                network_observations["direct_public_tcp"] = "connection_observed"
        except OSError:
            network_observations["direct_public_tcp"] = "connection_failed"
        for name, address in {
            "host_ssh": ("172.29.240.1", 22),
            "host_dns_tcp": ("172.29.240.1", 53),
        }.items():
            try:
                with socket.create_connection(address, timeout=2):
                    network_observations[name] = "connection_observed"
            except OSError:
                network_observations[name] = "connection_failed"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns_probe:
                dns_probe.settimeout(2)
                dns_probe.sendto(
                    b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
                    b"\x07example\x03com\x00\x00\x01\x00\x01",
                    ("172.29.240.1", 53),
                )
                dns_probe.recv(512)
                network_observations["host_dns_udp"] = "response_observed"
        except OSError:
            network_observations["host_dns_udp"] = "response_failed"
        content_hash = hashlib.sha256(
            json.dumps(
                [{"url": p["url"], "text": p["text"]} for p in pages],
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        result = {
            **pages[0],
            "complete": True,
            "pages": [
                {key: value for key, value in page.items() if index or key != "png_base64"}
                for index, page in enumerate(pages)
            ],
            "content_hash": content_hash,
            "uid": os.getuid(),
            "browser_version": browser.version,
            "chromium_sandbox_requested": True,
            "chromium_sandbox_text": sandbox_text,
            "network_observations": network_observations,
            "limits": {"text_per_page": 32768, "artifacts_per_source": MAX_BYTES},
            "scope": (
                "Capture and failed-request observations; independent policy proof still required"
            ),
        }
        browser.close()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Source-controlled error messages, URL parameters and browser stack traces are not output.
        code = "CAPTURE_FAILED"
        if isinstance(error, BrowserError):
            if match := re.search(r"net::(ERR_[A-Z_]+)", str(error)):
                code = match.group(1)
        elif isinstance(error, ValueError) and re.fullmatch(r"[A-Z_]{1,80}", str(error)):
            code = str(error)
        print(json.dumps({"complete": False, "error_class": type(error).__name__, "code": code}))
        raise SystemExit(1) from None
