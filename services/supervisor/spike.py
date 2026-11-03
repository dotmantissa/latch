"""Operator-run P0 worker probe, not the P4 private supervisor service."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parents[2]
SECCOMP_SHA256 = "cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849"


class WorkerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    image: str = Field(pattern=r"^[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}$")
    network: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$")
    proxy: str
    seccomp_file: Path = ROOT / "infra/browser/seccomp.json"

    @field_validator("network")
    @classmethod
    def dedicated_network(cls, value: str) -> str:
        if value in ("host", "bridge", "none", "default"):
            raise ValueError("A dedicated internal egress network is required")
        return value

    @field_validator("proxy")
    @classmethod
    def credential_free_proxy(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port is None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("An explicit credential-free internal HTTP proxy is required")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls) -> "WorkerSettings":
        values = {
            "image": os.environ.get("LATCH_BROWSER_IMAGE", ""),
            "network": os.environ.get("LATCH_EGRESS_NETWORK", ""),
            "proxy": os.environ.get("LATCH_EGRESS_PROXY", ""),
        }
        if os.environ.get("LATCH_SECCOMP_FILE"):
            values["seccomp_file"] = os.environ["LATCH_SECCOMP_FILE"]
        return cls(**values)


def docker_json(*arguments: str):
    result = subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    if len(result.stdout.encode()) > 2 * 1024 * 1024:
        raise ValueError("DOCKER_DIAGNOSTIC_TOO_LARGE")
    return json.loads(result.stdout)


def host_preflight(settings: WorkerSettings) -> dict:
    if shutil.which("docker") is None:
        raise ValueError("DOCKER_UNAVAILABLE")
    if hashlib.sha256(settings.seccomp_file.read_bytes()).hexdigest() != SECCOMP_SHA256:
        raise ValueError("SECCOMP_HASH_MISMATCH")
    info = docker_json("info", "--format", "{{json .}}")
    if "runsc" not in info.get("Runtimes", {}):
        raise ValueError("GVISOR_UNAVAILABLE")
    network = docker_json("network", "inspect", settings.network)[0]
    if network.get("Internal") is not True:
        raise ValueError("INTERNAL_NETWORK_REQUIRED")
    image = docker_json("image", "inspect", settings.image)[0]
    labels = image.get("Config", {}).get("Labels", {})
    if (
        labels.get("latch.playwright.version") != "1.64.1"
        or labels.get("latch.purpose") != "p0-browser-spike"
    ):
        raise ValueError("PINNED_SPIKE_IMAGE_REQUIRED")
    return {"image_digest": settings.image, "runtime": "runsc", "internal_network": True}


def cleanup_task(task_id: str) -> bool:
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise ValueError("INVALID_TASK_ID")
    name = "latch-p0-" + task_id
    result = subprocess.run(
        [
            "docker",
            "container",
            "ls",
            "--all",
            "--filter",
            f"name=^/{name}$",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    if not result.stdout.strip():
        return True
    container = docker_json("inspect", name)[0]
    if container.get("Config", {}).get("Labels", {}).get("latch.p0.task") != task_id:
        raise ValueError("CLEANUP_OWNERSHIP_MISMATCH")
    subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=15, check=True)
    result = subprocess.run(
        [
            "docker",
            "container",
            "ls",
            "--all",
            "--filter",
            f"name=^/{name}$",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return not result.stdout.strip()


def run_task(
    settings: WorkerSettings, payload: dict, timeout_seconds: int, task_id: str
) -> tuple[int, bytes, bool, bool]:
    name = "latch-p0-" + task_id
    command = [
        "docker",
        "create",
        "--interactive",
        "--name",
        name,
        "--label",
        "latch.p0.task=" + task_id,
        "--runtime",
        "runsc",
        "--user",
        "1000:1000",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--security-opt",
        "seccomp=" + str(settings.seccomp_file),
        "--cpus",
        "1.5",
        "--memory",
        "3g",
        "--memory-swap",
        "3g",
        "--pids-limit",
        "256",
        "--shm-size",
        "256m",
        "--log-driver",
        "none",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m,uid=1000,gid=1000,mode=1770",
        "--network",
        settings.network,
        settings.image,
    ]
    subprocess.run(command, capture_output=True, timeout=20, check=True)
    process = None
    buffers = [bytearray(), bytearray()]
    limits = [15 * 1024 * 1024, 64 * 1024]
    oversized = threading.Event()
    timed_out = threading.Event()

    def terminate():
        timed_out.set()
        if process is not None:
            process.kill()
        try:
            cleanup_task(task_id)
        except (OSError, ValueError, subprocess.SubprocessError):
            # Only the main thread can confirm cleanup and record its result.
            pass

    def drain(stream, index):
        while chunk := stream.read(65536):
            if len(buffers[index]) + len(chunk) > limits[index]:
                oversized.set()
                process.kill()
                return
            buffers[index].extend(chunk)

    try:
        container = docker_json("inspect", name)[0]
        host = container["HostConfig"]
        if (
            container["Config"]["User"] != "1000:1000"
            or not host["ReadonlyRootfs"]
            or host["Runtime"] != "runsc"
            or host["Privileged"]
            or host["NanoCpus"] != 1_500_000_000
            or host["Memory"] != 3 * 1024**3
            or host["MemorySwap"] != host["Memory"]
            or host["PidsLimit"] != 256
            or host.get("Binds")
            or host["NetworkMode"] != settings.network
            or host.get("CapAdd")
            or "ALL" not in (host.get("CapDrop") or [])
            or host.get("PortBindings")
        ):
            raise ValueError("CONTAINER_POLICY_NOT_EFFECTIVE")
        process = subprocess.Popen(
            ["docker", "start", "--attach", "--interactive", name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        watchdog = threading.Timer(timeout_seconds, terminate)
        watchdog.daemon = True
        watchdog.start()
        readers = [
            threading.Thread(target=drain, args=(stream, index), daemon=True)
            for index, stream in enumerate((process.stdout, process.stderr))
        ]
        for reader in readers:
            reader.start()
        try:
            body = json.dumps(payload).encode()
            if len(body) > 256 * 1024:
                raise ValueError("TASK_TOO_LARGE")
            process.stdin.write(body)
            process.stdin.close()
            process.wait(timeout=timeout_seconds + 5)
        except BrokenPipeError:
            process.wait(timeout=5)
        finally:
            watchdog.cancel()
            watchdog.join(timeout=20)
            if watchdog.is_alive():
                raise ValueError("WATCHDOG_CLEANUP_UNCONFIRMED")
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
        if oversized.is_set():
            raise ValueError("WORKER_OUTPUT_EXCEEDS_LIMITS")
        return process.returncode, bytes(buffers[0]), timed_out.is_set(), cleanup_task(task_id)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        cleanup_task(task_id)


def worker_probe(app_settings, timeout_probe: bool = False) -> dict:
    # Imports are deferred so the control runtime never imports Docker orchestration for model work.
    from services.common.preflight import load_task, write_report

    settings = WorkerSettings.from_environment()
    host = host_preflight(settings)
    task = load_task(app_settings)
    admitted = task.admitted_sources(datetime.now(UTC))
    source = task.sources[0]
    profile = next(profile for profile in task.profiles if profile.id == source.profile_id)
    pages = [{"url": admitted[0], "selector": profile.main_selector}]
    if profile.terms_url:
        if not profile.terms_selector:
            raise ValueError("TERMS_REGION_REQUIRED")
        pages.append({"url": profile.terms_url, "selector": profile.terms_selector})
    payload = {
        "mode": "timeout" if timeout_probe else "capture",
        "pages": pages,
        "asset_origins": [profile.origin, *profile.asset_origins],
        "proxy": settings.proxy,
    }
    task_id = uuid.uuid4().hex
    # Persist exact operation identity before creating the container, for interruption recovery.
    write_report(
        app_settings,
        "worker_active",
        {
            "status": "in_progress",
            "task_id": task_id,
            "mode": payload["mode"],
        },
    )
    exit_code, output, timed_out, cleaned = run_task(
        settings,
        payload,
        2 if timeout_probe else 90,
        task_id,
    )
    report = {
        "status": "pending_review",
        "scope": "actual_worker_observations",
        **host,
        "task_id": task_id,
        "timeout_observed": timed_out,
        "cleanup_observed": cleaned,
        "containment_proof": "Independent sandbox, firewall and proxy evidence review is required",
    }
    if not cleaned:
        raise ValueError("CLEANUP_NOT_CONFIRMED")
    if timeout_probe:
        if not timed_out:
            raise ValueError("WATCHDOG_PROBE_FAILED")
        write_report(app_settings, "worker_timeout", report)
    else:
        if exit_code != 0 or timed_out:
            raise ValueError("ACTUAL_CAPTURE_FAILED")
        capture = json.loads(output)
        if capture.get("complete") is not True or capture.get("uid") != 1000:
            raise ValueError("ACTUAL_CAPTURE_INVALID")
        write_report(app_settings, "capture", capture)
        report["capture_sha256"] = capture["png_sha256"]
        report["network_observations"] = capture["network_observations"]
        write_report(app_settings, "worker_capture", report)
    write_report(app_settings, "worker_active", {"status": "cleaned", "task_id": task_id})
    return report
