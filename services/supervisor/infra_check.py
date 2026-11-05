"""Actual infrastructure checks using a public technical page, without a buyer or supplier seed."""

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from services.supervisor.spike import WorkerSettings, host_preflight, run_task

DIRECTORY = Path("/var/lib/latch/infrastructure")


def save(name: str, value: dict):
    fd, temporary = tempfile.mkstemp(prefix=".probe-", dir=DIRECTORY)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, DIRECTORY / (name + ".json"))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    settings = WorkerSettings(
        image=Path("/var/lib/latch/provenance/browser-image.txt").read_text().strip(),
        network="latch_egress", proxy="http://172.29.240.1:3128",
    )
    host = host_preflight(settings)
    payload = {"mode": "capture", "pages": [{"url": "https://gvisor.dev/docs/",
                                             "selector": ".docs-content"}],
               "asset_origins": [], "proxy": settings.proxy}
    for name, seconds in (("timeout", 2), ("capture", 90)):
        task_id = uuid.uuid4().hex
        save("active", {"task_id": task_id, "mode": name, "status": "running"})
        payload["mode"] = name
        exit_code, output, timed_out, cleaned = run_task(settings, payload, seconds, task_id)
        save("active", {"task_id": task_id, "mode": name,
                        "status": "cleaned" if cleaned else "cleanup_unconfirmed"})
        report = {"at": datetime.now(UTC).isoformat(), "scope": "actual_worker_infrastructure",
                  "mode": name, "task_id": task_id, **host, "exit_code": exit_code,
                  "timeout_observed": timed_out, "cleanup_observed": cleaned}
        if name == "capture":
            capture = json.loads(output)
            save("documentation_capture", capture)
            report.update({key: capture.get(key) for key in (
                "complete", "uid", "browser_version", "chromium_sandbox_text",
                "png_sha256", "network_observations")})
            if exit_code != 0 or timed_out or capture.get("complete") is not True:
                save(name, report)
                raise ValueError("Actual infrastructure capture failed")
            if any(value not in ("request_failed", "connection_failed", "response_failed")
                   for value in capture["network_observations"].values()):
                save(name, report)
                raise ValueError("Forbidden network response observed")
        elif not timed_out:
            raise ValueError("Host watchdog did not terminate task")
        if not cleaned:
            raise ValueError("Container cleanup unconfirmed")
        save(name, report)
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
