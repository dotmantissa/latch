#!/usr/bin/env python3
"""Actual Neon/worker recovery with technical documentation in an isolated schema."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from services.api.settings import AppSettings
from services.common.source_policy import SourceProfile
from services.common.task_contracts import TaskRef
from services.runner.jobs import Runner
from services.runner.supervisor import SupervisorClient
from services.storage import evidence, jobs
from services.storage.database import database, direct_url, initialize

DIRECTORY = Path("var/runner-check")


def main():
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    settings = AppSettings.from_environment().model_copy(
        update={"database_schema": "latch_test_" + uuid4().hex,
                "evidence_dir": DIRECTORY / "sanitized"}
    )
    schema, url = settings.database_schema, settings.database_url()
    recovery = DIRECTORY / "active.json"
    recovery.write_text(json.dumps({"schema": schema, "phase": "initializing"}))
    client = SupervisorClient(Path("private/supervisor-tls"))
    process = None
    runner = None
    initialize(url, schema=schema)
    try:
        profile = SourceProfile(
            id="technical_documentation",
            version=1,
            origin="https://gvisor.dev",
            offer_paths=["/docs/"],
            main_selector=".docs-content",
            expires_at="2026-11-07T00:00:00Z",
        )
        owner, rid, source = uuid4(), uuid4(), uuid4()
        with database(url, schema=schema) as c:
            c.execute(
                "INSERT INTO users VALUES(%s,'technical_runner',"
                "'Runtime assertion','unused',true,1,1)",
                (owner,),
            )
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
            c.execute(
                "INSERT INTO request_versions VALUES(%s,1,%s,%s,1)",
                (rid, Jsonb({"scope": "technical_infrastructure_assertion"}), "assertion"),
            )
            c.execute(
                "INSERT INTO supplier_sources VALUES(%s,%s,1,'Technical documentation',"
                "%s,%s,1,'gvisor.dev')",
                (source, rid, "https://gvisor.dev/docs/", profile.id),
            )
            job = jobs.enqueue(c, owner, rid, 1, "technical_runner_recovery")
        environment = os.environ | {
            "LATCH_DB_SCHEMA": schema, "LATCH_EVIDENCE_DIR": str(settings.evidence_dir),
        }
        with (DIRECTORY / "child.log").open("w") as log:
            process = subprocess.Popen(
                [
                    ".venv/bin/python",
                    "-m",
                    "services.runner.jobs",
                    "--artifacts",
                    str(DIRECTORY / "quarantine"),
                ],
                env=environment,
                stdout=log,
                stderr=log,
            )
        recovery.write_text(
            json.dumps(
                {
                    "schema": schema,
                    "pid": process.pid,
                    "job_id": str(job["id"]),
                    "phase": "awaiting_actual_container",
                }
            )
        )
        started = time.monotonic()
        while time.monotonic() - started < 50:
            with database(url, schema=schema) as c:
                task = c.execute("SELECT * FROM job_tasks WHERE job_id=%s", (job["id"],)).fetchone()
                current = jobs.get(c, owner, job["id"])
            if task:
                inventory = subprocess.run(
                    [
                        "python3",
                        "scripts/worker_host.py",
                        "sudo",
                        "docker",
                        "container",
                        "ls",
                        "--filter",
                        "label=latch.task=" + task["task_id"].hex,
                        "--format",
                        "{{.Names}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                ).stdout.strip()
                if inventory == "latch-task-" + task["task_id"].hex:
                    break
            if process.poll() is not None:
                raise ValueError("Runner exited before actual task")
            time.sleep(0.5)
        else:
            raise ValueError("No actual runner container observed")
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        recovery.write_text(
            json.dumps(
                {
                    "schema": schema,
                    "job_id": str(job["id"]),
                    "old_fence": str(current["fence"]),
                    "old_holder": str(current["lease_holder"]),
                    "task_id": str(task["task_id"]),
                    "phase": "awaiting_real_lease_expiry",
                }
            )
        )
        print("Actual runner killed while its browser container was running.", flush=True)
        while True:
            with database(url, schema=schema) as c:
                current = jobs.get(c, owner, job["id"])
                remaining = current["lease_until"] - jobs.clock(c)
            if remaining <= 0:
                break
            time.sleep(min(2, remaining / 1000))
        runner = Runner(settings, client, DIRECTORY / "recovered-quarantine")
        runner.reconcile()
        with database(url, schema=schema) as c:
            recovered = jobs.claim(c, runner.holder)
        assert recovered["attempt"] == 2 and recovered["fence"] != current["fence"]
        print(
            "Expired attempt cleanup confirmed; second attempt claimed with a new fence.",
            flush=True,
        )
        runner.run(recovered)
        with database(url, schema=schema) as c:
            final = jobs.get(c, owner, job["id"])
            captures = c.execute(
                "SELECT * FROM job_tasks WHERE job_id=%s ORDER BY started_at", (job["id"],)
            ).fetchall()
            events = c.execute(
                "SELECT kind FROM events WHERE job_id=%s ORDER BY id", (job["id"],)
            ).fetchall()
            packets = evidence.views(c, owner, rid, 1)
        assert final["state"] == "succeeded" and len(captures) == 2
        assert all(t["cleanup_at"] is not None for t in captures)
        assert captures[0]["outcome"] == "interrupted" and captures[1]["outcome"] == "captured"
        assert (
            DIRECTORY / "recovered-quarantine" / (captures[1]["task_id"].hex + ".capture")
        ).is_file()
        assert len(packets) == 1 and len(packets[0].pages) == 1
        artifact = packets[0].pages[0]
        assert runner.evidence.read(artifact.sanitized_hash)
        report = {
            "status": "passed",
            "scope": "actual_isolated_Neon_and_worker_runner_recovery",
            "supplier_acceptance": "pending",
            "attempts": 2,
            "actual_runner_killed_during_browser": True,
            "real_lease_expired": True,
            "fresh_fence": True,
            "cleanup_before_retry": True,
            "durable_sanitized_evidence": True,
            "final_state": final["state"],
            "events": [e["kind"] for e in events],
        }
        (DIRECTORY / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if runner:
            runner.evidence.close()
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        with database(url, schema=schema) as c:
            active = c.execute("SELECT job_id,fence FROM job_attempts").fetchall()
        for attempt in active:
            client.revoke(TaskRef(job_id=attempt["job_id"], fence=attempt["fence"]))
        client.close()
        with psycopg.connect(direct_url(url), connect_timeout=10) as c:
            c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        recovery.unlink()


if __name__ == "__main__":
    main()
