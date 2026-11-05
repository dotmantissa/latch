#!/usr/bin/env python3
"""Actual managed-worker checks using technical documentation, never a supplier/buyer seed."""

import hashlib
import json
import ssl
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

from services.common.task_contracts import TaskCommand, TaskRef
from services.runner.supervisor import SupervisorClient, SupervisorRejected, SupervisorUnavailable

DIRECTORY = Path("var/supervisor-check")


def remote(*args):
    return subprocess.run(
        ["python3", "scripts/worker_host.py", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=40,
    ).stdout.strip()


def command():
    return TaskCommand(
        job_id=uuid4(),
        fence=uuid4(),
        task_id=uuid4(),
        profile_id="technical_documentation",
        profile_version=1,
        url="https://gvisor.dev/docs/",
    )


def main():
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    client = SupervisorClient(Path("private/supervisor-tls"))
    active = DIRECTORY / "active.json"
    report = {
        "scope": "actual_private_supervisor_technical_documentation",
        "supplier_acceptance": "pending",
    }
    try:
        context = ssl.create_default_context(cafile="private/supervisor-tls/ca.crt")
        try:
            with httpx.Client(verify=context, trust_env=False, timeout=5) as unauth:
                unauth.post("https://127.0.0.1:9443/v1/tasks", json={})
        except httpx.HTTPError:
            report["missing_client_certificate_denied"] = True
        else:
            raise ValueError("Unauthenticated mTLS request reached HTTP")
        for mode in ("capture", "cancel", "restart"):
            task = command()
            active.write_text(task.model_dump_json())
            ref = TaskRef(job_id=task.job_id, fence=task.fence)
            accepted = client.submit(task)
            assert client.submit(task)["task_id"] == accepted["task_id"]
            try:
                client.action(task.task_id, TaskRef(job_id=task.job_id, fence=uuid4()), "status")
            except SupervisorRejected as error:
                assert str(error) == "TASK_FENCE_MISMATCH"
            else:
                raise ValueError("Wrong task fence admitted")
            start, heartbeat = time.monotonic(), 0.0
            if mode in ("cancel", "restart"):
                # Independently observe an actual running owned container before interruption.
                observed = False
                while time.monotonic() - start < 15:
                    inventory = remote(
                        "sudo",
                        "docker",
                        "container",
                        "ls",
                        "--filter",
                        "label=latch.task=" + task.task_id.hex,
                        "--format",
                        "{{.Names}}",
                    )
                    if inventory == "latch-task-" + task.task_id.hex:
                        observed = True
                        break
                    time.sleep(0.5)
                assert observed, "No running task observed for interruption check"
                if mode == "cancel":
                    client.action(task.task_id, ref, "cancel")
                else:
                    remote("sudo", "systemctl", "restart", "latch-supervisor.service")
            while time.monotonic() - start < 95:
                try:
                    status = client.action(task.task_id, ref, "status")
                except SupervisorUnavailable:
                    if mode != "restart":
                        raise
                    time.sleep(0.5)
                    continue
                if status["cleanup_confirmed"]:
                    break
                if mode == "capture" and time.monotonic() - heartbeat > 8:
                    client.action(task.task_id, ref, "heartbeat")
                    heartbeat = time.monotonic()
                time.sleep(0.5)
            assert status["cleanup_confirmed"]
            if mode == "capture":
                assert status["state"] == "succeeded", status
                target = DIRECTORY / "documentation.capture"
                client.artifact(task.task_id, ref, target, status["artifact_hash"])
                assert hashlib.sha256(target.read_bytes()).hexdigest() == status["artifact_hash"]
            else:
                assert status["state"] == ("cancelled" if mode == "cancel" else "interrupted"), (
                    status
                )
            assert not remote(
                "sudo",
                "docker",
                "container",
                "ls",
                "--all",
                "--filter",
                "label=latch.task=" + task.task_id.hex,
                "--format",
                "{{.Names}}",
            )
            report[mode] = status | {"actual_container_cleanup": True}
            print(json.dumps({"check": mode, "state": status["state"]}), flush=True)
        task = command()
        ref = TaskRef(job_id=task.job_id, fence=task.fence)
        assert client.revoke(ref)["revoked"]
        try:
            client.submit(task)
        except SupervisorRejected as error:
            assert str(error) == "TASK_FENCE_REVOKED"
            report["delayed_revoked_fence_denied"] = True
        else:
            raise ValueError("Revoked late submission admitted")
        report["at"] = remote("date", "--utc", "--iso-8601=seconds")
        report["status"] = "passed"
        (DIRECTORY / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        active.unlink()
        print(json.dumps(report, indent=2), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    main()
