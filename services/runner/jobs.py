"""Separate durable runner. Network work occurs outside every Postgres transaction."""

import argparse
import json
import os
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from services.api.settings import AppSettings
from services.artifacts.packet import prepare
from services.artifacts.store import ArtifactStore
from services.common.source_policy import SourceProfile
from services.common.task_contracts import TaskCommand, TaskRef
from services.runner.supervisor import SupervisorClient, SupervisorRejected, SupervisorUnavailable
from services.storage import evidence, jobs
from services.storage.database import database


class Runner:
    def __init__(self, settings: AppSettings, client: SupervisorClient, artifacts: Path):
        self.url, self.schema = settings.database_url(), settings.database_schema
        self.client, self.holder = client, uuid4()
        self.artifacts = artifacts
        artifacts.mkdir(mode=0o700, parents=True, exist_ok=True)
        if artifacts.is_symlink() or artifacts.stat().st_mode & 0o077:
            raise ValueError("PRIVATE_QUARANTINE_REQUIRED")
        self.stop = threading.Event()
        self.evidence = ArtifactStore(settings.evidence_dir)

    def db(self):
        return database(self.url, schema=self.schema)

    def cleanup(self, job, tasks):
        ref = TaskRef(job_id=job["id"], fence=job["fence"])
        # Revocation is durable on the worker before checking absence: a delayed old submission
        # can never create a container after recovery has recorded an absent task as cleaned.
        self.client.revoke(ref)
        for task in tasks:
            try:
                status = self.client.action(task["task_id"], ref, "cancel")
                deadline = time.monotonic() + 20
                while not status["cleanup_confirmed"]:
                    if time.monotonic() >= deadline:
                        raise SupervisorUnavailable("CLEANUP_NOT_CONFIRMED")
                    self.stop.wait(0.5)
                    status = self.client.action(task["task_id"], ref, "status")
            except SupervisorRejected as error:
                if str(error) != "TASK_NOT_FOUND":
                    raise
            with self.db() as c:
                jobs.task_cleaned(
                    c, job["id"], job["fence"], job["lease_holder"], task["task_id"], "interrupted"
                )

    def reconcile(self):
        with self.db() as c:
            expired = jobs.expired(c)
        for job in expired:
            with self.db() as c:
                tasks = c.execute(
                    "SELECT * FROM job_tasks WHERE job_id=%s AND cleanup_at IS NULL", (job["id"],)
                ).fetchall()
            self.cleanup(job, tasks)
            with self.db() as c:
                jobs.recover(c, job["id"], job["fence"], job["lease_holder"])

    def run(self, job):
        ref = TaskRef(job_id=job["id"], fence=job["fence"])
        with self.db() as c:
            sources = c.execute(
                "SELECT s.*,p.profile_json,p.active,p.expires_at FROM supplier_sources s "
                "JOIN source_profiles p ON p.id=s.profile_id AND p.version=s.profile_version "
                "WHERE s.request_id=%s AND s.version=%s ORDER BY s.id",
                (job["request_id"], job["request_version"]),
            ).fetchall()
        succeeded = bool(sources)
        try:
            for source in sources:
                profile = SourceProfile.model_validate(source["profile_json"])
                if not source["active"] or source["expires_at"] <= int(time.time() * 1000):
                    raise ValueError("PROFILE_EXPIRED")
                url = profile.admit(source["canonical_public_url"], datetime.now(UTC))
                with self.db() as c:
                    live = jobs.heartbeat(c, job["id"], job["fence"], self.holder)
                    if live["cancel_requested_at"] or self.stop.is_set():
                        succeeded = False
                        break
                    task = jobs.start_task(c, job["id"], job["fence"], self.holder, source["id"])
                self.client.submit(
                    TaskCommand(
                        task_id=task["task_id"],
                        job_id=job["id"],
                        fence=job["fence"],
                        profile_id=profile.id,
                        profile_version=profile.version,
                        url=url,
                    )
                )
                last_heartbeat = 0.0
                while True:
                    if time.monotonic() - last_heartbeat >= 8:
                        with self.db() as c:
                            live = jobs.heartbeat(c, job["id"], job["fence"], self.holder)
                        last_heartbeat = time.monotonic()
                        if live["cancel_requested_at"] or self.stop.is_set():
                            succeeded = False
                            break
                        self.client.action(task["task_id"], ref, "heartbeat")
                    status = self.client.action(task["task_id"], ref, "status")
                    if status["cleanup_confirmed"]:
                        if status["state"] == "succeeded":
                            target = self.artifacts / (task["task_id"].hex + ".capture")
                            self.client.artifact(
                                task["task_id"], ref, target, status["artifact_hash"]
                            )
                            packet = prepare(target.read_bytes(), profile, url, self.evidence)
                            outcome, digest = "captured", status["artifact_hash"]
                        else:
                            outcome, digest, succeeded = "failed", None, False
                        with self.db() as c:
                            jobs.task_cleaned(
                                c,
                                job["id"],
                                job["fence"],
                                self.holder,
                                task["task_id"],
                                outcome,
                                digest,
                            )
                            if outcome == "captured":
                                evidence.save_capture(
                                    c, job["id"], job["fence"], self.holder,
                                    task["task_id"], packet,
                                )
                        break
                    self.stop.wait(0.5)
                if not succeeded:
                    break
        except jobs.FenceLost:
            # Old attempts can only revoke/clean their own worker fence, never write active state.
            self.client.revoke(ref)
            return
        except (SupervisorUnavailable, ValueError, OSError):
            succeeded = False
        with self.db() as c:
            pending = c.execute(
                "SELECT * FROM job_tasks WHERE job_id=%s AND cleanup_at IS NULL", (job["id"],)
            ).fetchall()
        if pending:
            self.cleanup(job, pending)
        with self.db() as c:
            jobs.finish(c, job["id"], job["fence"], self.holder, success=succeeded)

    def loop(self):
        while not self.stop.is_set():
            try:
                self.reconcile()
                with self.db() as c:
                    job = jobs.claim(c, self.holder)
                if job:
                    self.run(job)
            except Exception:
                # Errors leave durable leases/tasks for fenced reconciliation. No raw DB/URLs.
                print(
                    json.dumps({"event": "runner_retry", "code": "RUNNER_UNAVAILABLE"}), flush=True
                )
            self.stop.wait(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls", type=Path, default=Path("private/supervisor-tls"))
    parser.add_argument("--artifacts", type=Path, default=Path("var/quarantine"))
    args = parser.parse_args()
    os.umask(0o077)
    client = SupervisorClient(args.tls)
    runner = Runner(AppSettings.from_environment(), client, args.artifacts)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: runner.stop.set())
    try:
        runner.loop()
    finally:
        runner.evidence.close()
        client.close()


if __name__ == "__main__":
    main()
