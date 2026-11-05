"""Real Neon authority/atomicity assertions. No supplier or buyer acceptance is claimed."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from services.api.auth import new_session, provision_user, session_row
from services.api.errors import ApiError
from services.artifacts.packet import Packet, Page
from services.artifacts.sanitize import sanitize
from services.common.source_policy import SourceProfile
from services.domain.contracts import RequestInput, content_hash
from services.domain.correspondence import ProposedCorrespondence
from services.domain.correspondence import ground as ground_image
from services.domain.decisions import ApprovalInput, SelectionInput
from services.domain.extraction import ProposedTerms, ground
from services.domain.releases import ReleaseInput
from services.domain.reviews import ReviewInput, decide
from services.storage import decisions, evidence, jobs, releases
from services.storage import requests as requests_store
from services.storage.database import database
from tests.test_artifacts import png
from tests.test_domain import worksheet_data
from tests.test_extraction import supported


class RollbackScenario(Exception):
    pass


def seed(c):
    owner = provision_user(
        c, "release_assertion", "Security assertion only", secrets.token_urlsafe(24)
    )
    token = new_session(c, owner)
    session = session_row(c, token)
    profile = SourceProfile(
        id="release_assertion",
        version=1,
        origin="https://vendor.example.com",
        offer_paths=["/assertion"],
        main_selector="main",
        product_image_review=True,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    c.execute(
        "INSERT INTO source_profiles VALUES(%s,1,%s,true,%s)",
        (
            profile.id,
            Jsonb(profile.model_dump(mode="json")),
            int(profile.expires_at.timestamp() * 1000),
        ),
    )
    body = worksheet_data()
    body["items"][0].update(key="assertion", required_units=1)
    body["sources"] = [
        {
            "label": "Security assertion only",
            "url": profile.origin + "/assertion",
            "profile_id": profile.id,
            "profile_version": 1,
        }
    ]
    saved = requests_store.save(c, owner, RequestInput.model_validate(body), "seed_assertion")
    source = c.execute(
        "SELECT id FROM supplier_sources WHERE request_id=%s", (saved.id,)
    ).fetchone()["id"]
    job = jobs.enqueue(c, owner, saved.id, 1, "seed_assertion")
    job = jobs.claim(c, uuid4())
    task = jobs.start_task(c, job["id"], job["fence"], job["lease_holder"], source)
    raster = sanitize(png())
    text = (
        "Security price assertion $12.34\n"
        + "Scope separation assertion. " * 8
        + "\nShipping assertion $0.00"
    )
    at = datetime.fromtimestamp(jobs.clock(c) / 1000, UTC)
    packet = Packet(
        "a" * 64,
        "b" * 64,
        profile.id,
        1,
        (
            Page(
                0,
                profile.origin + "/assertion",
                text,
                hashlib.sha256(text.encode()).hexdigest(),
                at,
                at,
                raster,
            ),
        ),
    )
    jobs.task_cleaned(
        c,
        job["id"],
        job["fence"],
        job["lease_holder"],
        task["task_id"],
        "captured",
        packet.capture_hash,
    )
    capture = evidence.save_capture(
        c, job["id"], job["fence"], job["lease_holder"], task["task_id"], packet
    )
    quote = "Security price assertion $12.34"
    line = {"item_key": "assertion"} | {
        k: supported(v, quote)
        for k, v in {
            "coverage": "quoted",
            "exact_match": True,
            "sell_unit_size": 1,
            "min_sell_units": 1,
            "price_cents": 1234,
            "available_units": 100,
        }.items()
    }
    values = {
        "lines": [line],
        "shipping_cents": supported(0, "Shipping assertion $0.00"),
        "tax_included": supported(True, quote),
        "conditions_satisfied": supported(True, quote),
        "latest_arrival": supported((datetime.now(UTC) + timedelta(days=2)).isoformat(), quote),
    }
    extraction = ground(
        ProposedTerms.model_validate(values),
        [{"text": text}],
        source_id=source,
        capture_hash=packet.capture_hash,
        model_id="security_assertion",
        expected_item_keys={"assertion"},
    )
    usage = {
        "calls": 1,
        "capture_sha256": packet.capture_hash,
        "attempts": [
            {
                "model": "security_assertion",
                "elapsed_ms": 1,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ],
    }
    jobs.heartbeat(c, job["id"], job["fence"], job["lease_holder"])
    extracted = evidence.save_extraction(
        c, job["id"], job["fence"], job["lease_holder"], capture["id"], extraction, usage
    )
    image = ground_image(
        ProposedCorrespondence(
            observations=[
                {
                    "page_index": 0,
                    "item_key": k,
                    "status": "agrees",
                    "reason": "visible_match",
                    "evidence": [{"page_index": 0, "quote": quote}],
                    "region": [0, 0, raster.width, raster.height],
                }
                for k in (None, "assertion")
            ]
        ),
        source_id=source,
        capture_hash=packet.capture_hash,
        pages=[
            {
                "text": text,
                "sanitized_hash": raster.sanitized_hash,
                "width": raster.width,
                "height": raster.height,
            }
        ],
        item_keys={"assertion"},
        model_id="security_assertion",
    )
    evidence.save_correspondence(
        c, job["id"], job["fence"], job["lease_holder"], capture["id"], image, usage
    )
    jobs.finish(c, job["id"], job["fence"], job["lease_holder"], success=True)
    # Individual decision rules are exercised; direct inserts save round trips in this
    # transition assertion. The review API has its own actual authenticated checks.
    for n, field in enumerate(extraction.fields, 1):
        command = ReviewInput(
            request_version=1,
            expected_review_version=n - 1,
            proposal_hash=extraction.proposal_hash,
            item_key=field.item_key,
            kind=field.kind,
            action="confirm",
            corrected_value=None,
            evidence=[{"page_index": s.page_index, "quote": s.quote} for s in field.spans],
            reason=None,
            evidence_seen=True,
        )
        decision = decide(field, command, [{"text": text}], packet.capture_hash)
        c.execute(
            "INSERT INTO field_reviews VALUES(%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                extracted["id"],
                n,
                owner,
                extraction.proposal_hash,
                Jsonb(decision.model_dump(mode="json")),
                Jsonb(command.model_dump(mode="json")),
                f"review_{n}",
                content_hash(command.model_dump(mode="json")),
                jobs.clock(c),
            ),
        )
    c.execute("INSERT INTO review_heads VALUES(%s,%s)", (extracted["id"], len(extraction.fields)))
    comparison = decisions.compare(c, owner, saved.id, 1)
    assert comparison.current and comparison.sources[0].selectable
    select_body = SelectionInput(
        request_version=1,
        comparison_id=comparison.id,
        comparison_hash=comparison.packet_hash,
        source_id=source,
        expected_revision=0,
    )
    selected = decisions.choose(c, owner, saved.id, select_body, "choose_assertion")
    approve_body = ApprovalInput(
        request_version=1,
        selection_id=selected.id,
        comparison_hash=comparison.packet_hash,
        scope_seen=True,
    )
    approved = decisions.approve(c, owner, saved.id, session, approve_body, "approve_assertion")
    return owner, saved.id, session, approved, capture, extracted, select_body, approve_body, packet


def fresh_assertion(
    c, owner, rid, session, approval, old_capture, *, changed=False, stale=False, commit_stale=False
):
    command = ReleaseInput(
        request_version=1,
        approval_id=approval.id,
        approval_hash=approval.packet_hash,
        scope_seen=True,
    )
    attempt = releases.begin(c, owner, rid, session, command, "release_assertion")
    job = jobs.claim(c, uuid4())
    at = jobs.clock(c)
    # Explicit database transition assertion, without pretending a browser recaptured.
    task_id, capture_id, page_id = uuid4(), uuid4(), uuid4()
    source = old_capture["source_id"]
    c.execute(
        "INSERT INTO job_tasks VALUES(%s,%s,%s,%s,%s,%s,'captured',%s)",
        (task_id, job["id"], job["fence"], source, at, at, "c" * 64),
    )
    c.execute(
        "INSERT INTO source_captures SELECT %s,owner_id,request_id,request_version,%s,%s,%s,"
        "source_id,%s,%s,fingerprint_version,profile_id,profile_version,page_count,%s "
        "FROM source_captures WHERE id=%s",
        (
            capture_id,
            job["id"],
            job["fence"],
            task_id,
            "c" * 64,
            "d" * 64 if changed else old_capture["content_fingerprint"],
            at,
            old_capture["id"],
        ),
    )
    time = at - 61000 if stale else at
    if commit_stale:
        observed = c.execute(
            "WITH moment AS MATERIALIZED (SELECT floor(extract(epoch FROM "
            "clock_timestamp())*1000)::bigint AS at) INSERT INTO captured_pages "
            "SELECT %s,%s,page_index,source_url,source_text,text_hash,m.at-59900,m.at-59900,"
            "raw_png_hash,sanitized_png_hash,sanitized_bytes,width,height,sanitizer_version "
            "FROM captured_pages CROSS JOIN moment m WHERE capture_id=%s "
            "RETURNING floor(extract(epoch FROM clock_timestamp())*1000)::bigint"
            "-completed_at AS age",
            (page_id, capture_id, old_capture["id"]),
        ).fetchone()["age"]
        assert 59900 <= observed < 60000
        c.execute("UPDATE jobs SET created_at=%s WHERE id=%s", (at - 90000, job["id"]))
        c.execute("SELECT pg_sleep(0.2)")
    else:
        c.execute(
            "INSERT INTO captured_pages SELECT %s,%s,page_index,source_url,source_text,text_hash,"
            "%s,%s,raw_png_hash,sanitized_png_hash,sanitized_bytes,width,height,sanitizer_version "
            "FROM captured_pages WHERE capture_id=%s",
            (page_id, capture_id, time, time, old_capture["id"]),
        )
    c.execute(
        "UPDATE jobs SET state='succeeded',finished_at=%s,lease_until=NULL WHERE id=%s",
        (at, job["id"]),
    )
    return attempt, command


def test_atomic_receipt_and_authority_guards_on_real_neon(neon_store):
    url, schema = neon_store
    with database(url, schema=schema) as c:
        owner, rid, session, approval, capture, extracted, select_body, approve_body, packet = seed(
            c
        )
    # Run each negative transition inside a rollback savepoint against the same immutable baseline.
    for mutation in (
        "revoked",
        "session",
        "profile",
        "review",
        "selection",
        "version",
        "stale",
        "changed",
        "cancelled",
    ):
        with database(url, schema=schema) as c:
            try:
                with c.transaction():
                    attempt, _ = fresh_assertion(
                        c,
                        owner,
                        rid,
                        session,
                        approval,
                        capture,
                        changed=mutation == "changed",
                        stale=mutation == "stale",
                    )
                    if mutation == "revoked":
                        decisions.revoke(c, owner, approval.id)
                    elif mutation == "cancelled":
                        assert releases.cancel(c, owner, attempt.id).state == "blocked"
                    elif mutation == "session":
                        c.execute(
                            "UPDATE sessions SET revoked_at=%s WHERE id=%s",
                            (jobs.clock(c), session["id"]),
                        )
                    elif mutation == "profile":
                        c.execute(
                            "UPDATE source_profiles SET active=false WHERE id=%s",
                            (packet.profile_id,),
                        )
                    elif mutation == "review":
                        c.execute(
                            "UPDATE review_heads SET version=version+1 WHERE extraction_id=%s",
                            (extracted["id"],),
                        )
                    elif mutation == "selection":
                        newer = select_body.model_copy(update={"expected_revision": 1})
                        decisions.choose(c, owner, rid, newer, "new_choice_assertion")
                    elif mutation == "version":
                        c.execute(
                            "INSERT INTO request_versions SELECT request_id,2,snapshot_json,"
                            "content_hash,created_at FROM request_versions "
                            "WHERE request_id=%s AND version=1",
                            (rid,),
                        )
                        c.execute("UPDATE requests SET current_version=2 WHERE id=%s", (rid,))
                    releases.finalize(c, attempt.id)
                    result = releases.view(c, owner, attempt.id)
                    assert result.state in ("blocked", "changed") and result.receipt_id is None
                    assert c.execute("SELECT count(*) AS n FROM receipts").fetchone()["n"] == 0
                    if mutation == "changed":
                        assert (
                            decisions.approval_view(
                                c,
                                c.execute(
                                    "SELECT * FROM approvals WHERE id=%s", (approval.id,)
                                ).fetchone(),
                            ).state
                            == "revoked"
                        )
                    raise RollbackScenario
            except RollbackScenario:
                pass
    with database(url, schema=schema) as c:
        attempt, command = fresh_assertion(c, owner, rid, session, approval, capture)
        releases.finalize(c, attempt.id)
        result = releases.view(c, owner, attempt.id)
        assert result.state == "released" and result.receipt_id is not None
        assert (
            releases.begin(c, owner, rid, session, command, "release_assertion").receipt_id
            == result.receipt_id
        )
        releases.finalize(c, attempt.id)
        receipt = releases.receipt(c, owner, result.receipt_id)
        assert receipt.record_hash == content_hash(receipt.record)
        assert c.execute("SELECT count(*) AS n FROM receipts").fetchone()["n"] == 1
        with pytest.raises(ApiError):
            releases.receipt(c, uuid4(), result.receipt_id)
        with pytest.raises(ApiError):
            releases.view(c, uuid4(), attempt.id)
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("UPDATE receipts SET record_hash=%s", ("f" * 64,))
