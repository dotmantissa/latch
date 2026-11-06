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
from services.common.source_policy import SourceProfile
from services.common.task_contracts import TaskCommand, TaskRef
from services.domain.contracts import RequestItem
from services.runner.correspondence import correspond
from services.runner.extraction import extract
from services.runner.planning import plan_inspection
from services.runner.supervisor import SupervisorClient, SupervisorRejected, SupervisorUnavailable
from services.runner.vultr import ProviderFailure, VultrClient
from services.storage import evidence, inspections, jobs, releases
from services.storage.database import database


class Runner:
    def __init__(
        self, settings: AppSettings, client: SupervisorClient, artifacts: Path, *, on_invalid=None,
    ):
        self.url, self.schema = settings.database_url(), settings.database_schema
        self.client, self.holder = client, uuid4()
        self.settings = settings
        self.on_invalid = on_invalid
        self.checked_at = {}
        self.artifacts = artifacts
        artifacts.mkdir(mode=0o700, parents=True, exist_ok=True)
        if artifacts.is_symlink() or artifacts.stat().st_mode & 0o077:
            raise ValueError("PRIVATE_QUARANTINE_REQUIRED")
        self.stop = threading.Event()
        self.evidence = settings.artifact_store()

    def db(self):
        return database(self.url, schema=self.schema)

    def checkpoint(self, job, profile):
        if self.stop.is_set():
            raise ValueError("RUNNER_STOPPED")
        key = (job["id"], job["fence"], profile.id, profile.version)
        # Consecutive pre/post-call hooks share the same five-second authority poll.
        # Durable writes and final publication always perform their own locked checks.
        if time.monotonic() - self.checked_at.get(key, float("-inf")) < 5:
            return
        with self.db() as c:
            evidence.current(c, job["id"], job["fence"], self.holder, renew=True)
            evidence.active_profile(c, profile.id, profile.version)
        self.checked_at[key] = time.monotonic()

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
        self.checked_at.clear()
        ref = TaskRef(job_id=job["id"], fence=job["fence"])
        with self.db() as c:
            sources = c.execute(
                "SELECT s.*,p.profile_json,p.active,p.expires_at FROM supplier_sources s "
                "JOIN source_profiles p ON p.id=s.profile_id AND p.version=s.profile_version "
                "WHERE s.request_id=%s AND s.version=%s ORDER BY s.id",
                (job["request_id"], job["request_version"]),
            ).fetchall()
            # Never read private specifications, budget, delivery notes or identity
            # into the inference input. The public projection is also revalidated.
            rows = c.execute(
                "SELECT stable_item_key AS key,public_specification,required_units "
                "FROM required_items WHERE request_id=%s AND version=%s ORDER BY ordered_position",
                (job["request_id"], job["request_version"]),
            ).fetchall()
            remaining = max(0, (job["deadline_at"] - jobs.clock(c)) / 1000)
        deadline = time.monotonic() + remaining
        succeeded = bool(sources)
        extraction_calls_remaining = 8
        failure_code = "TASK_FAILED"
        try:
            items = [RequestItem(specification=r["public_specification"], **r) for r in rows]
            if not 1 <= len(items) <= 3 or not 1 <= len(sources) <= 3:
                raise ValueError("INSPECTION_INPUT_SET_INVALID")
            if job["kind"] == "inspect":
                first = SourceProfile.model_validate(sources[0]["profile_json"])
                plan, usage = plan_inspection(
                    VultrClient(self.settings, output_token_limit=4096), items, sources,
                    deadline=deadline, checkpoint=lambda: self.checkpoint(job, first),
                )
                with self.db() as c:
                    inspections.save_plan(c, job, self.holder, plan, usage)
                sources = [next(s for s in sources if s["id"] == sid) for sid in plan.source_order]
            for source_index, source in enumerate(sources):
                profile = SourceProfile.model_validate(source["profile_json"])
                if not source["active"] or source["expires_at"] <= int(time.time() * 1000):
                    raise ValueError("PROFILE_EXPIRED")
                url = profile.admit(source["canonical_public_url"], datetime.now(UTC))
                self.checkpoint(job, profile)
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
                                saved = evidence.save_capture(
                                    c, job["id"], job["fence"], self.holder,
                                    task["task_id"], packet,
                                )
                        if outcome == "captured" and job["kind"] == "inspect":
                            self.checkpoint(job, profile)
                            with self.db() as c:
                                live = evidence.current(c, job["id"], job["fence"], self.holder)
                                jobs.event(c, live, "extraction_started")
                            proposal, usage = extract(
                                VultrClient(self.settings, output_token_limit=4096),
                                target.read_bytes(), source_id=source["id"], items=items,
                                expected_pages=[{"url": page.url} for page in packet.pages],
                                deadline=deadline,
                                on_invalid=self.on_invalid,
                                checkpoint=lambda profile=profile: self.checkpoint(job, profile),
                                max_calls=min(3, extraction_calls_remaining
                                              - (len(sources) - source_index - 1)),
                            )
                            extraction_calls_remaining -= usage["calls"]
                            self.checkpoint(job, profile)
                            with self.db() as c:
                                evidence.save_extraction(
                                    c, job["id"], job["fence"], self.holder,
                                    saved["id"], proposal, usage,
                                )
                            observation, image_usage = correspond(
                                VultrClient(self.settings, output_token_limit=4096),
                                packet, source["id"], items, deadline=deadline,
                                on_invalid=self.on_invalid,
                                checkpoint=lambda profile=profile: self.checkpoint(job, profile),
                            )
                            with self.db() as c:
                                evidence.save_correspondence(
                                    c, job["id"], job["fence"], self.holder,
                                    saved["id"], observation, image_usage,
                                )
                        break
                    self.stop.wait(0.5)
                if not succeeded:
                    break
        except jobs.FenceLost:
            # Old attempts can only revoke/clean their own worker fence, never write active state.
            self.client.revoke(ref)
            return
        except ProviderFailure as error:
            code = str(error)
            if len(code) > 100 or not code or any(
                ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for ch in code
            ):
                code = "INFERENCE_FAILED"
            print(json.dumps({"event": "inference_failed", "code": code}), flush=True)
            failure_code = code
            succeeded = False
        except (SupervisorUnavailable, ValueError, OSError) as error:
            code = str(error)
            if len(code) > 100 or not code or any(
                ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for ch in code
            ):
                code = "TASK_FAILED"
            failure_code = code
            print(json.dumps({"event": "inspection_failed", "code": code}), flush=True)
            succeeded = False
        with self.db() as c:
            pending = c.execute(
                "SELECT * FROM job_tasks WHERE job_id=%s AND cleanup_at IS NULL", (job["id"],)
            ).fetchall()
        if pending:
            self.cleanup(job, pending)
        try:
            with self.db() as c:
                jobs.finish(c, job["id"], job["fence"], self.holder, success=succeeded,
                            failure_code=failure_code)
        except jobs.FenceLost as error:
            self.client.revoke(ref)
            print(json.dumps({"event": "publication_fenced", "code": str(error)}), flush=True)
        except ValueError:
            with self.db() as c:
                jobs.finish(c, job["id"], job["fence"], self.holder, success=False)

    def loop(self):
        monitor = threading.Thread(target=self.monitor, daemon=True)
        monitor.start()
        while not self.stop.is_set():
            try:
                self.reconcile()
                with self.db() as c:
                    finished = releases.reconcile(c)
                for attempt in finished:
                    with self.db() as c:
                        releases.finalize(c, attempt)
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
        monitor.join(timeout=20)

    def monitor(self):
        import httpx

        from services.common.config import read_secret

        checked = float("-inf")
        provider_ready = False
        while not self.stop.is_set():
            available, profiles = False, []
            try:
                if time.monotonic()-checked >= 300:
                    provider_ready = False
                    if self.settings.inference_key_file and self.settings.model_id:
                        with httpx.Client(timeout=10, trust_env=False) as client:
                            response = client.get(
                                self.settings.inference_base_url+"/models",
                                headers={"Authorization": "Bearer "+read_secret(
                                    self.settings.inference_key_file)},
                            )
                        if response.status_code == 200 and len(response.content) <= 1024*1024:
                            provider_ready = any(p.get("id") == self.settings.model_id
                                                 for p in response.json().get("data", []))
                    checked = time.monotonic()
                profiles = self.client.health()
                available = provider_ready
            except Exception:
                pass
            try:
                with self.db() as c:
                    inspections.heartbeat(c, self.holder, available, profiles)
            except Exception:
                pass
            self.stop.wait(10)
        try:
            with self.db() as c:
                inspections.heartbeat(c, self.holder, False, [])
        except Exception:
            pass


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
