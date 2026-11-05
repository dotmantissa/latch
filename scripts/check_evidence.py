#!/usr/bin/env python3
"""Actual public source research through worker, Vultr, isolated Neon and authenticated PNG API."""

import argparse
import hashlib
import importlib
import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from services.api.app import create_app
from services.api.auth import provision_user
from services.api.errors import ApiError
from services.api.settings import AppSettings
from services.artifacts.packet import prepare
from services.artifacts.store import ArtifactStore
from services.common.config import Settings
from services.common.source_policy import SourceProfile
from services.common.task_contracts import TaskCommand, TaskRef
from services.domain.contracts import RequestInput, RequestItem
from services.domain.extraction import unreviewed_offer
from services.domain.reviews import ReviewInput
from services.runner.extraction import extract
from services.runner.supervisor import SupervisorClient
from services.runner.vultr import VultrClient
from services.storage import evidence, jobs, reviews
from services.storage.database import database, direct_url, initialize

DIRECTORY = Path("var/evidence-check")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review-commands",
        action="store_true",
        help="Automated review protocol assertions, not actual human acceptance",
    )
    parser.add_argument(
        "--browser-review",
        action="store_true",
        help="Real browser review assertions on genuine evidence, not human buyer acceptance",
    )
    parser.add_argument(
        "--browser-retry",
        action="store_true",
        help="Keep the isolated fixture for up to ten minutes between local browser repairs",
    )
    args = parser.parse_args()
    if args.browser_retry and not args.browser_review:
        parser.error("Browser retries require --browser-review")
    if args.review_commands and args.browser_review:
        parser.error(
            "Run protocol and browser checks separately; both mutate isolated review state"
        )
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    settings = AppSettings.from_environment().model_copy(
        update={
            "database_schema": "latch_test_" + uuid4().hex,
            "evidence_dir": DIRECTORY / "sanitized",
        }
    )
    url, schema = settings.database_url(), settings.database_schema
    client = SupervisorClient(Path("private/supervisor-tls"))
    recovery = DIRECTORY / "active.json"
    recovery.write_text(json.dumps({"schema": schema, "phase": "initializing"}))
    stop = threading.Event()
    pulse = None
    command = None

    def db():
        return database(url, schema=schema)

    try:
        initialize(url, schema=schema)
        profile = SourceProfile(
            id="ubiquiti_u6plus_research",
            version=1,
            origin="https://store.ui.com",
            offer_paths=["/us/en/products/u6-plus"],
            main_selector="main",
            asset_origins=["https://assets.ecomm.ui.com", "https://cdn.ecomm.ui.com"],
            expires_at="2026-11-07T00:00:00Z",
        )
        public_url = profile.origin + profile.offer_paths[0]
        password = secrets.token_urlsafe(24)
        rid, source, holder = uuid4(), uuid4(), uuid4()
        item = RequestItem(
            key="u6_plus",
            specification="Ubiquiti Access Point U6 Plus",
            public_specification="Ubiquiti Access Point U6 Plus",
            required_units=1,
        )
        snapshot = {"scope": "public_source_evidence_boundary_research"}
        if args.browser_review:
            # Explicit UI assertion constraints, never a real buyer's budget/deadline/consent.
            deadline = (datetime.now(UTC) + timedelta(days=7)).replace(second=0, microsecond=0)
            snapshot = RequestInput(
                name="Supplier evidence UI assertion",
                currency="USD",
                budget="1.00",
                required_by=deadline,
                timezone="UTC",
                required_by_local=deadline.strftime("%Y-%m-%dT%H:%M"),
                delivery_basis="Automated UI assertion only; no buyer requirement or acceptance",
                items=[item],
                sources=[
                    {
                        "label": "U6 Plus public source research",
                        "url": public_url,
                        "profile_id": profile.id,
                        "profile_version": profile.version,
                    }
                ],
            ).snapshot()
        with db() as c:
            owner = provision_user(c, "evidence_research", "Public source research", password)
            other = provision_user(c, "evidence_other", "Ownership boundary assertion", password)
            c.execute(
                "INSERT INTO source_profiles VALUES(%s,1,%s,true,%s)",
                (
                    profile.id,
                    Jsonb(profile.model_dump(mode="json")),
                    int(profile.expires_at.timestamp() * 1000),
                ),
            )
            c.execute(
                "INSERT INTO requests(id,owner_id,current_version,created_at,updated_at) "
                "VALUES(%s,%s,1,1,1)",
                (rid, owner),
            )
            # Infrastructure assertion rows in an isolated schema. No invented buyer budget,
            # deadline, consent, application worksheet, supplier acceptance or purchase order.
            c.execute(
                "INSERT INTO request_versions VALUES(%s,1,%s,'research',1)",
                (
                    rid,
                    Jsonb(snapshot),
                ),
            )
            c.execute(
                "INSERT INTO supplier_sources VALUES(%s,%s,1,'U6 Plus research',%s,%s,1,%s)",
                (source, rid, public_url, profile.id, "store.ui.com"),
            )
            c.execute(
                "INSERT INTO required_items VALUES(%s,%s,1,%s,%s,%s,1,0)",
                (
                    uuid4(),
                    rid,
                    item.key,
                    item.specification,
                    item.public_specification,
                ),
            )
            job = jobs.enqueue(c, owner, rid, 1, "source_evidence_boundary")
            job = jobs.claim(c, holder)
            task = jobs.start_task(c, job["id"], job["fence"], holder, source)
        command = TaskCommand(
            task_id=task["task_id"],
            job_id=job["id"],
            fence=job["fence"],
            profile_id=profile.id,
            profile_version=profile.version,
            url=public_url,
        )
        ref = TaskRef(job_id=job["id"], fence=job["fence"])
        recovery.write_text(
            json.dumps(
                {
                    "schema": schema,
                    "command": command.model_dump(mode="json"),
                    "phase": "capture",
                }
            )
        )

        def heartbeat():
            while not stop.wait(5):
                try:
                    with db() as c:
                        jobs.heartbeat(c, job["id"], job["fence"], holder)
                except Exception:
                    return  # Main's fenced writes still fail closed if renewal was lost.

        pulse = threading.Thread(target=heartbeat, daemon=True)
        pulse.start()
        client.submit(command)
        started, ping = time.monotonic(), 0.0
        while time.monotonic() - started < 95:
            status = client.action(command.task_id, ref, "status")
            if status["cleanup_confirmed"]:
                break
            if time.monotonic() - ping > 8:
                client.action(command.task_id, ref, "heartbeat")
                ping = time.monotonic()
            time.sleep(0.5)
        if status["state"] != "succeeded" or not status["cleanup_confirmed"]:
            raise ValueError("ACTUAL_SOURCE_CAPTURE_FAILED")
        raw_file = DIRECTORY / "source.capture"
        client.artifact(command.task_id, ref, raw_file, status["artifact_hash"])
        raw = raw_file.read_bytes()
        with ArtifactStore(settings.evidence_dir) as files:
            packet = prepare(raw, profile, public_url, files)
        (DIRECTORY / "source.sanitized.png").write_bytes(packet.pages[0].raster.data)
        print("Actual supplier capture cleaned and separately sanitized.", flush=True)
        proposal, usage = extract(
            VultrClient(
                Settings(
                    model_id="qwen3.8-flash-next",
                    inference_key_file=Path("private/vultr-inference-key"),
                ),
                output_token_limit=4096,
            ),
            raw,
            source_id=source,
            items=[item],
            expected_pages=[{"url": public_url}],
            on_invalid=lambda value: (DIRECTORY / f"invalid-{value['attempt']}.json").write_text(
                json.dumps(value, indent=2) + "\n"
            ),
        )
        offer = unreviewed_offer(proposal)
        assert not offer.terms_reviewed and not any(line.reviewed for line in offer.lines)
        price = next(f for f in proposal.fields if f.kind == "price_cents")
        assert price.state == "ambiguous" and price.value is None
        with db() as c:
            jobs.task_cleaned(
                c, job["id"], job["fence"], holder, command.task_id, "captured", packet.capture_hash
            )
            saved = evidence.save_capture(
                c,
                job["id"],
                job["fence"],
                holder,
                command.task_id,
                packet,
            )
            assert (
                evidence.save_capture(
                    c,
                    job["id"],
                    job["fence"],
                    holder,
                    command.task_id,
                    packet,
                )["id"]
                == saved["id"]
            )
            extracted = evidence.save_extraction(
                c, job["id"], job["fence"], holder, saved["id"], proposal, usage
            )
            assert (
                evidence.save_extraction(
                    c, job["id"], job["fence"], holder, saved["id"], proposal, usage
                )["id"]
                == extracted["id"]
            )
            artifact_id = c.execute(
                "SELECT id FROM captured_pages WHERE capture_id=%s", (saved["id"],)
            ).fetchone()["id"]
        with db() as c:
            try:
                evidence.artifact(c, owner, artifact_id)
            except ApiError as error:
                assert error.status == 404
            else:
                raise ValueError("RUNNING_ATTEMPT_PUBLISHED_EVIDENCE")
            assert jobs.finish(c, job["id"], job["fence"], holder, success=True)["state"] == (
                "succeeded"
            )
        stop.set()
        pulse.join(timeout=15)
        with db() as c:
            views = evidence.views(c, owner, rid, 1)
            assert len(views) == 1 and views[0].extraction == proposal
            assert views[0].review_state == "unreviewed"
            assert evidence.artifact(c, owner, artifact_id)["sanitized_png_hash"] == (
                packet.pages[0].raster.sanitized_hash
            )
            try:
                evidence.artifact(c, other, artifact_id)
            except ApiError as error:
                assert error.status == 404
            else:
                raise ValueError("OTHER_OWNER_READ_EVIDENCE")
        for table in ("source_captures", "captured_pages", "source_extractions"):
            try:
                with db() as c:
                    c.execute(sql.SQL("UPDATE {} SET id=id").format(sql.Identifier(table)))
            except psycopg.errors.RaiseException:
                pass
            else:
                raise ValueError("EVIDENCE_RECORD_MUTABLE")
        try:
            with db() as c:
                evidence.save_capture(c, job["id"], uuid4(), holder, command.task_id, packet)
        except jobs.FenceLost:
            pass
        else:
            raise ValueError("OLD_FENCE_PERSISTED_EVIDENCE")
        app = create_app(settings)
        path = f"/api/v1/artifacts/{artifact_id}"
        protocol = None
        with TestClient(app, base_url=settings.public_origin) as browser:
            assert browser.get(path).status_code == 401
            logged = browser.post(
                "/api/v1/auth/login",
                json={
                    "username": "evidence_research",
                    "password": password,
                },
                headers={"Origin": settings.public_origin},
            )
            assert logged.status_code == 200
            response = browser.get(path, headers={"Accept": "image/png"})
            assert response.status_code == 200
            assert response.content == packet.pages[0].raster.data
            assert response.headers["content-type"] == "image/png"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["cross-origin-resource-policy"] == "same-origin"
            if args.review_commands:
                review_path = f"/api/v1/extractions/{extracted['id']}/reviews"
                view_path = f"/api/v1/extractions/{extracted['id']}/review"
                initial = browser.get(view_path)
                assert initial.status_code == 200
                assert initial.json()["data"]["checked_fields"] == 0
                assert initial.headers["etag"] == '"0"'
                headers = {
                    "Origin": settings.public_origin,
                    "X-CSRF-Token": logged.json()["data"]["csrf_token"],
                    "If-Match": '"0"',
                    "Idempotency-Key": "protocol_price_basis",
                }
                body = {
                    "request_version": 1,
                    "expected_review_version": 0,
                    "proposal_hash": proposal.proposal_hash,
                    "item_key": price.item_key,
                    "kind": "price_cents",
                    "action": "correct",
                    "corrected_value": 14200,
                    "evidence": [
                        {"page_index": s.page_index, "quote": s.quote} for s in price.spans
                    ],
                    "reason": "Automated protocol assertion using captured surcharge amount",
                    "evidence_seen": True,
                }
                denied = browser.post(
                    review_path,
                    json=body,
                    headers={
                        "Origin": settings.public_origin,
                        "If-Match": '"0"',
                        "Idempotency-Key": "no_csrf_assertion",
                    },
                )
                assert denied.status_code == 403
                unknown = browser.post(
                    review_path,
                    json=body
                    | {
                        "action": "confirm",
                        "corrected_value": None,
                    },
                    headers=headers | {"Idempotency-Key": "ambiguous_confirm_assertion"},
                )
                assert unknown.status_code == 422
                corrected = browser.post(review_path, json=body, headers=headers)
                assert corrected.status_code == 201
                assert corrected.json()["data"]["decision"]["value"] == 14200
                repeated = browser.post(review_path, json=body, headers=headers)
                assert repeated.status_code == 201
                assert repeated.json()["data"]["id"] == corrected.json()["data"]["id"]
                assert (
                    browser.post(
                        review_path, json=body | {"corrected_value": 12900}, headers=headers
                    ).status_code
                    == 409
                )
                assert (
                    browser.post(
                        review_path,
                        json=body,
                        headers=headers | {"Idempotency-Key": "stale_tab_assertion"},
                    ).status_code
                    == 412
                )
                disputed = browser.post(
                    review_path,
                    json=body
                    | {
                        "expected_review_version": 1,
                        "action": "dispute",
                        "corrected_value": None,
                        "reason": "Automated protocol assertion: tax basis remains unresolved",
                    },
                    headers=headers
                    | {"If-Match": '"1"', "Idempotency-Key": "price_dispute_assertion"},
                )
                assert disputed.status_code == 201
                current_view = browser.get(view_path).json()["data"]
                assert current_view["review_version"] == 2 and current_view["checked_fields"] == 0
                retained = next(
                    f for f in current_view["fields"] if f["original"]["kind"] == "price_cents"
                )
                assert retained["original"]["state"] == "ambiguous"
                assert retained["original"]["value"] is None and retained["value"] is None
                history = browser.get(review_path + "?limit=1").json()["data"]
                assert len(history["items"]) == 1 and history["next_before"] == 2
                prior_page = browser.get(review_path + "?limit=1&before=2").json()["data"]
                assert prior_page["items"][0]["decision"]["value"] == 14200

                def concurrent_review(index):
                    try:
                        with db() as c:
                            return reviews.save(
                                c,
                                owner,
                                extracted["id"],
                                ReviewInput.model_validate(body | {"expected_review_version": 2}),
                                f"concurrent_review_{index}",
                            ).version
                    except ApiError as error:
                        return error.status

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(concurrent_review, range(2)))
                assert sorted(results) == [3, 412]
                reset = browser.post(
                    review_path,
                    json=body
                    | {
                        "expected_review_version": 3,
                        "action": "dispute",
                        "corrected_value": None,
                        "reason": "Automated protocol assertion leaves source basis unresolved",
                    },
                    headers=headers
                    | {"If-Match": '"3"', "Idempotency-Key": "final_dispute_assertion"},
                )
                assert reset.status_code == 201
                assert browser.get(view_path).json()["data"]["checked_fields"] == 0
                try:
                    with db() as c:
                        c.execute("UPDATE field_reviews SET id=id")
                except psycopg.errors.RaiseException:
                    pass
                else:
                    raise ValueError("FIELD_REVIEW_HISTORY_MUTABLE")
                with db() as c:
                    c.execute("UPDATE requests SET current_version=2 WHERE id=%s", (rid,))
                assert (
                    browser.post(
                        review_path,
                        json=body | {"expected_review_version": 2},
                        headers=headers
                        | {"If-Match": '"2"', "Idempotency-Key": "changed_request_assertion"},
                    ).status_code
                    == 412
                )
                assert browser.get(view_path).json()["data"]["current"] is False
                assert browser.get(review_path).status_code == 200
                protocol = {
                    "automated": True,
                    "observed_human_review": False,
                    "csrf_unknown_confirm_idempotency_stale_and_request_checks": True,
                    "source_price_correction_and_dispute": True,
                    "concurrent_compare_and_swap": True,
                    "append_only_review_rows": True,
                    "original_proposal_and_paginated_history_preserved": True,
                }
            target = settings.evidence_dir / (packet.pages[0].raster.sanitized_hash + ".png")
            original = target.read_bytes()
            target.write_bytes(b"x" * len(original))
            assert browser.get(path).status_code == 503
            target.write_bytes(original)
        with TestClient(app, base_url=settings.public_origin) as browser:
            assert (
                browser.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "evidence_other",
                        "password": password,
                    },
                    headers={"Origin": settings.public_origin},
                ).status_code
                == 200
            )
            assert browser.get(path).status_code == 404
            if args.review_commands:
                assert browser.get(view_path).status_code == 404
                assert browser.get(review_path).status_code == 404
                assert (
                    browser.post(
                        review_path,
                        json=body | {"expected_review_version": 2},
                        headers={
                            "Origin": settings.public_origin,
                            "X-CSRF-Token": browser.get("/api/v1/auth/session").json()["data"][
                                "csrf_token"
                            ],
                            "If-Match": '"2"',
                            "Idempotency-Key": "other_owner_assertion",
                        },
                    ).status_code
                    == 404
                )
        browser_protocol = None
        if args.browser_review:
            from scripts import check_review_browser

            while True:
                try:
                    browser_protocol = importlib.reload(check_review_browser).check_browser(
                        settings, rid, password
                    )
                    break
                except Exception as error:
                    if not args.browser_retry:
                        raise
                    print(str(error).replace(password, "[redacted]"), flush=True)
                    print(
                        "Browser check failed; isolated fixture waits for local retry marker.",
                        flush=True,
                    )
                    retry = Path("var/review-browser/retry")
                    retry.unlink(missing_ok=True)
                    started = time.monotonic()
                    while not retry.exists() and time.monotonic() - started < 600:
                        time.sleep(0.5)
                    if not retry.exists():
                        raise RuntimeError(
                            "Browser retry deadline expired; fixture cleaned"
                        ) from None
                    retry.unlink()
        report = {
            "scope": "actual_public_source_evidence_boundary_in_isolated_schema",
            "status": "passed",
            "application_buyer_data_created": False,
            "capture_cleanup_confirmed": True,
            "sanitized_raster": True,
            "png_sha256": hashlib.sha256(response.content).hexdigest(),
            "width": packet.pages[0].raster.width,
            "height": packet.pages[0].raster.height,
            "actual_vultr_calls": usage["calls"],
            "price_state": price.state,
            "human_reviewed": False,
            "durable_capture_and_extraction": True,
            "idempotency": True,
            "running_attempt_hidden": True,
            "wrong_fence_denied": True,
            "immutable_rows": True,
            "authenticated_png_headers_and_hash": True,
            "other_owner_denied": True,
            "corrupted_file_unavailable": True,
            "buyer_acceptance_and_release": "pending",
            "review_protocol": protocol,
            "browser_review_protocol": browser_protocol,
        }
        (DIRECTORY / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        stop.set()
        if pulse:
            pulse.join(timeout=15)
        if command:
            client.revoke(TaskRef(job_id=command.job_id, fence=command.fence))
        client.close()
        with psycopg.connect(direct_url(url), connect_timeout=10) as c:
            c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        recovery.unlink()


if __name__ == "__main__":
    main()
