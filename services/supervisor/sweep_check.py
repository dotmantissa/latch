"""Actual independent sweep against a stopped operator diagnostic executor on the worker."""

import argparse
import json
import os
import pwd
import signal
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

from services.common.task_contracts import TaskCommand
from services.supervisor.server import load
from services.supervisor.spike import cleanup_task, docker_json, run_task
from services.supervisor.tasks import boot_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child")
    args = parser.parse_args()
    config = argparse.Namespace(
        config=Path("/var/lib/latch/supervisor.json"), state=Path("/var/lib/latch/tasks")
    )
    tasks = load(config)
    if args.child:
        task_id = UUID(args.child)
        payload = {
            "mode": "timeout",
            "pages": [{"url": "https://gvisor.dev/docs/", "selector": ".docs-content"}],
            "asset_origins": [],
            "proxy": tasks.settings.proxy,
        }
        run_task(tasks.settings, payload, 90, task_id.hex, scope="task")
        return
    if pwd.getpwuid(os.geteuid()).pw_name != "latch-supervisor":
        raise ValueError("Trusted operator must run this check as the supervisor service user")
    command = TaskCommand(
        job_id=uuid4(),
        fence=uuid4(),
        task_id=uuid4(),
        profile_id="technical_documentation",
        profile_version=1,
        url="https://gvisor.dev/docs/",
    )
    evidence = tasks.registry.root / ".sweep-check"
    evidence.mkdir(mode=0o700, exist_ok=True)
    process = None
    at = time.time()
    with tasks.registry.locked():
        if any(not r["cleanup_confirmed"] for r in tasks.registry.rows()):
            raise ValueError("No active worker task may overlap this diagnostic")
        row = command.model_dump(mode="json") | {
            "command": command.model_dump(mode="json"),
            "state": "running",
            "accepted_at": at,
            "last_clock": at,
            "lease_until": at + 12,
            "deadline_at": at + 90,
            "boot_id": boot_id(),
            "cleanup_confirmed": False,
            "artifact_hash": None,
            "scope": "operator_independent_sweeper_diagnostic",
        }
        tasks.registry.save(row)
    (evidence / "active.json").write_text(json.dumps({"task_id": command.task_id.hex}))
    try:
        process = subprocess.Popen(
            [
                "/opt/latch/host-venv/bin/python",
                "-m",
                "services.supervisor.sweep_check",
                "--child",
                command.task_id.hex,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started = time.monotonic()
        while time.monotonic() - started < 8:
            try:
                if docker_json("inspect", "latch-task-" + command.task_id.hex)[0]["State"][
                    "Running"
                ]:
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.2)
        else:
            raise ValueError("Actual diagnostic container was not observed")
        os.kill(process.pid, signal.SIGSTOP)
        while time.monotonic() - started < 30:
            try:
                docker_json("inspect", "latch-task-" + command.task_id.hex)
            except subprocess.CalledProcessError:
                break
            time.sleep(0.5)
        else:
            raise ValueError("Independent sweep did not remove overdue container")
        # The stopped Python executor cannot run its own watchdog or cleanup.
        assert Path(f"/proc/{process.pid}/status").read_text().split("State:")[1].lstrip()[0] == "T"
        assert tasks.registry.load(command.task_id)["state"] == "cleanup_pending"
        os.kill(process.pid, signal.SIGCONT)
        process.wait(timeout=15)
        tasks.sweep(restart=True)
        assert cleanup_task(command.task_id.hex, scope="task")
        report = {
            "status": "passed",
            "scope": "actual_independent_sweeper_diagnostic",
            "actual_running_container_observed": True,
            "executor_stopped_with_SIGSTOP": True,
            "real_lease_seconds": 12,
            "timer_removed_container": True,
            "cleanup_pending_until_reconciliation": True,
            "cleanup_confirmed": True,
        }
        (evidence / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        (evidence / "active.json").unlink()
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if process and process.poll() is None:
            os.kill(process.pid, signal.SIGCONT)
            process.kill()
            process.wait(timeout=10)
        cleanup_task(command.task_id.hex, scope="task")
        tasks.sweep(restart=True)


if __name__ == "__main__":
    main()
