#!/usr/bin/env python3
"""Actual durable runner supplier research in isolated Neon, with no buyer acceptance."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from services.api.settings import AppSettings
from services.common.source_policy import SourceProfile
from services.common.task_contracts import TaskRef
from services.domain.extraction import revalidate, unreviewed_offer
from services.runner.jobs import Runner
from services.runner.supervisor import SupervisorClient
from services.storage import evidence, jobs
from services.storage.database import database, direct_url, initialize

DIRECTORY = Path("var/runner-extraction-check")


def main():
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    settings = AppSettings.from_environment().model_copy(update={
        "database_schema": "latch_test_" + uuid4().hex,
        "evidence_dir": DIRECTORY / "sanitized", "model_id": "qwen3.8-flash-next",
        "inference_key_file": Path("private/vultr-inference-key"),
    })
    url, schema = settings.database_url(), settings.database_schema
    recovery = DIRECTORY / "active.json"
    recovery.write_text(json.dumps({"schema": schema, "phase": "initializing"}))
    client = SupervisorClient(Path("private/supervisor-tls"))
    runner = None
    initialized = False

    def db():
        return database(url, schema=schema)

    try:
        initialize(url, schema=schema)
        initialized = True
        profile = SourceProfile(
            id="ubiquiti_u6plus_research", version=1, origin="https://store.ui.com",
            offer_paths=["/us/en/products/u6-plus"], main_selector="main",
            asset_origins=["https://assets.ecomm.ui.com", "https://cdn.ecomm.ui.com"],
            expires_at="2026-11-07T00:00:00Z",
        )
        owner, rid, source = uuid4(), uuid4(), uuid4()
        with db() as c:
            c.execute(
                "INSERT INTO users VALUES(%s,'runner_source_research',"
                "'Public source research','unused',true,1,1)", (owner,),
            )
            c.execute(
                "INSERT INTO source_profiles VALUES(%s,1,%s,true,%s)",
                (profile.id, Jsonb(profile.model_dump(mode="json")),
                 int(profile.expires_at.timestamp() * 1000)),
            )
            c.execute(
                "INSERT INTO requests(id,owner_id,current_version,created_at,updated_at) "
                "VALUES(%s,%s,1,1,1)", (rid, owner),
            )
            c.execute(
                "INSERT INTO request_versions VALUES(%s,1,%s,'research',1)",
                (rid, Jsonb({"scope": "public_source_runner_boundary_research"})),
            )
            c.execute(
                "INSERT INTO required_items VALUES(%s,%s,1,'u6_plus',"
                "'Private projection denial assertion',"
                "'Ubiquiti Access Point U6 Plus',1,0)", (uuid4(), rid),
            )
            c.execute(
                "INSERT INTO supplier_sources VALUES(%s,%s,1,'U6 Plus research',%s,%s,1,%s)",
                (source, rid, profile.origin + profile.offer_paths[0], profile.id, "store.ui.com"),
            )
            jobs.enqueue(c, owner, rid, 1, "durable_source_extraction")
        def invalid(value):
            (DIRECTORY / f"invalid-{value['attempt']}.json").write_text(
                json.dumps(value, indent=2) + "\n",
            )

        runner = Runner(settings, client, DIRECTORY / "quarantine", on_invalid=invalid)
        with db() as c:
            job = jobs.claim(c, runner.holder)
        recovery.write_text(json.dumps({
            "schema": schema, "job_id": str(job["id"]), "fence": str(job["fence"]),
            "phase": "actual_runner_capture_and_inference",
        }))
        print("Running fresh public supplier capture and bounded durable extraction.", flush=True)
        runner.run(job)
        with db() as c:
            final = jobs.get(c, owner, job["id"])
            packets = evidence.views(c, owner, rid, 1)
            tasks = c.execute("SELECT * FROM job_tasks WHERE job_id=%s", (job["id"],)).fetchall()
            events = c.execute(
                "SELECT kind FROM events WHERE job_id=%s ORDER BY id", (job["id"],),
            ).fetchall()
            extraction_row = c.execute(
                "SELECT e.* FROM source_extractions e JOIN source_captures c ON c.id=e.capture_id "
                "WHERE c.job_id=%s AND c.fence=%s", (job["id"], job["fence"]),
            ).fetchone()
        summary = {
            "state": final["state"], "failure_code": final["failure_code"],
            "events": [e["kind"] for e in events],
            "proposal_stored": extraction_row is not None,
        }
        (DIRECTORY / "phase-result.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary), flush=True)
        assert final["state"] == "succeeded", "RUNNER_DID_NOT_SUCCEED"
        assert len(tasks) == 1 and tasks[0]["cleanup_at"] and tasks[0]["outcome"] == "captured"
        assert len(packets) == 1 and packets[0].extraction is not None
        packet = packets[0]
        proposal = packet.extraction
        revalidate(proposal, [{"text": p.source_text} for p in packet.pages], {"u6_plus"})
        offer = unreviewed_offer(proposal)
        assert not offer.terms_reviewed and all(not line.reviewed for line in offer.lines)
        price = next(f for f in proposal.fields if f.kind == "price_cents")
        assert price.state == "ambiguous" and price.value is None, "PRICE_CONFLICT_NOT_RETAINED"
        for page in packet.pages:
            raster = runner.evidence.read(page.sanitized_hash)
            assert hashlib.sha256(raster).hexdigest() == page.sanitized_hash
        assert [e["kind"] for e in events] == [
            "job_queued", "job_started", "capture_stored", "extraction_started",
            "extraction_stored", "job_succeeded",
        ]
        report = {
            "status": "passed", "scope": "actual_isolated_supplier_runner_extraction",
            "application_buyer_data_created": False, "human_reviewed": False,
            "buyer_acceptance_and_release": "pending", "cleanup_confirmed": True,
            "durable_sanitized_capture": True, "durable_grounded_extraction": True,
            "complete_fenced_publication": True,
            "actual_vultr_calls": extraction_row["usage_json"]["calls"],
            "price_state": price.state, "price_cents": price.value,
            "events": [e["kind"] for e in events],
        }
        (DIRECTORY / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        try:
            if initialized:
                with db() as c:
                    attempts = c.execute("SELECT job_id,fence FROM job_attempts").fetchall()
                for attempt in attempts:
                    client.revoke(TaskRef(job_id=attempt["job_id"], fence=attempt["fence"]))
        finally:
            if runner:
                runner.evidence.close()
            client.close()
        with psycopg.connect(direct_url(url), connect_timeout=10) as c:
            c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        recovery.unlink()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Raw connection/provider errors and source content never enter terminal output.
        print(json.dumps({
            "status": "failed", "code": type(error).__name__,
            "assertion": str(error) if isinstance(error, AssertionError) else None,
        }), flush=True)
        raise SystemExit(1) from None
