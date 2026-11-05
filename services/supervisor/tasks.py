"""Worker-local durable quarantine and lifecycle. Application records remain in Neon."""

import base64
import fcntl
import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from services.common.source_policy import SourceProfile
from services.common.task_contracts import TaskCommand, TaskRef
from services.supervisor.spike import WorkerSettings, cleanup_task, run_task

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "timed_out", "interrupted"})


class TaskError(ValueError):
    pass


class Registry:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o077:
            raise TaskError("PRIVATE_REGISTRY_REQUIRED")
        self.thread_lock = threading.RLock()

    @contextmanager
    def locked(self):
        with self.thread_lock, (self.root / ".lock").open("a+b") as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            yield

    def write(self, name: str, body: bytes):
        fd, path = tempfile.mkstemp(prefix=".write-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(body)
                out.flush()
                os.fsync(out.fileno())
            os.replace(path, self.root / name)
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def save(self, row):
        self.write(UUID(row["task_id"]).hex + ".json", json.dumps(row).encode())

    def load(self, task_id: UUID):
        path = self.root / (task_id.hex + ".json")
        if not path.exists():
            raise TaskError("TASK_NOT_FOUND")
        return json.loads(path.read_bytes())

    def rows(self):
        return [self.load(UUID(path.stem)) for path in sorted(self.root.glob("*.json"))]


def capture_artifact(output: bytes, payload: dict) -> str:
    """Worker output is untrusted; validate the entire bounded capture before accepting it."""
    if len(output) > 15 * 1024 * 1024:
        raise TaskError("ARTIFACT_TOO_LARGE")
    value = json.loads(output)
    if value.get("complete") is not True or value.get("uid") != 1000:
        raise TaskError("CAPTURE_INCOMPLETE")
    pages = value.get("pages")
    if not isinstance(pages, list) or len(pages) != len(payload["pages"]):
        raise TaskError("CAPTURE_PAGE_SET")
    total = 0
    for index, (page, target) in enumerate(zip(pages, payload["pages"], strict=True)):
        if page["url"] != target["url"] or page["observed_urls"] != [target["url"]]:
            raise TaskError("CAPTURE_URL_CHAIN")
        if page["status"] != 200:
            raise TaskError("CAPTURE_STATUS")
        text = page["text"].encode()
        png = base64.b64decode(
            value["png_base64"] if index == 0 else page["png_base64"], validate=True
        )
        total += len(text) + len(png)
        if not text.strip() or len(text) > 32768 or total > 10 * 1024 * 1024:
            raise TaskError("CAPTURE_CONTENT_LIMIT")
        if len(png) < 33 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
            raise TaskError("CAPTURE_PNG")
        width, height = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
        if (
            type(page["width"]) is not int
            or type(page["height"]) is not int
            or ((page["width"], page["height"]) != (width, height))
            or not 1 <= width <= 4000
            or not 1 <= height <= 16000
        ):
            raise TaskError("CAPTURE_DIMENSIONS")
        for data, key in ((text, "text_sha256"), (png, "png_sha256")):
            if hashlib.sha256(data).hexdigest() != page[key]:
                raise TaskError("CAPTURE_HASH")
        start = datetime.fromisoformat(page["started_at"])
        end = datetime.fromisoformat(page["completed_at"])
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or not 0 <= (end - start).total_seconds() <= 90
        ):
            raise TaskError("CAPTURE_INTERVAL")
    return hashlib.sha256(output).hexdigest()


class Tasks:
    def __init__(self, registry: Registry, settings: WorkerSettings, profiles: list[SourceProfile]):
        self.registry, self.settings = registry, settings
        self.profiles = {(p.id, p.version): p for p in profiles}
        if len(self.profiles) != len(profiles):
            raise TaskError("DUPLICATE_PROFILE")
        self.events: dict[str, threading.Event] = {}

    def payload(self, command: TaskCommand):
        profile = self.profiles.get((command.profile_id, command.profile_version))
        if profile is None:
            raise TaskError("PROFILE_NOT_ADMITTED")
        url = profile.admit(command.url, datetime.now(UTC))
        pages = [{"url": url, "selector": profile.main_selector}]
        if profile.terms_url:
            if not profile.terms_selector:
                raise TaskError("TERMS_REGION_REQUIRED")
            pages.append({"url": profile.terms_url, "selector": profile.terms_selector})
        return {
            "mode": "capture",
            "pages": pages,
            "asset_origins": [profile.origin, *profile.asset_origins],
            "proxy": self.settings.proxy,
        }

    @staticmethod
    def authorized(row, ref: TaskRef):
        if row["job_id"] != str(ref.job_id) or row["fence"] != str(ref.fence):
            raise TaskError("TASK_FENCE_MISMATCH")

    def submit(self, command: TaskCommand):
        payload = self.payload(command)
        with self.registry.locked():
            if (self.registry.root / f"{command.job_id.hex}.{command.fence.hex}.revoked").exists():
                raise TaskError("TASK_FENCE_REVOKED")
            try:
                row = self.registry.load(command.task_id)
            except TaskError as error:
                if str(error) != "TASK_NOT_FOUND":
                    raise
            else:
                if row["command"] != command.model_dump(mode="json"):
                    raise TaskError("TASK_IDEMPOTENCY_MISMATCH")
                return self.view(row)
            if any(
                row["state"] not in TERMINAL or not row["cleanup_confirmed"]
                for row in self.registry.rows()
            ):
                raise TaskError("WORKER_BUSY")
            if len(self.registry.rows()) >= 1000:
                raise TaskError("TASK_RETENTION_CAP")
            at = time.time()
            row = command.model_dump(mode="json") | {
                "command": command.model_dump(mode="json"),
                "state": "accepted",
                "accepted_at": at,
                "last_clock": at,
                "lease_until": at + 30,
                "deadline_at": at + 90,
                "boot_id": boot_id(),
                "cleanup_confirmed": False,
                "artifact_hash": None,
            }
            self.registry.save(row)
            cancelled = self.events[command.task_id.hex] = threading.Event()
            thread = threading.Thread(
                target=self.execute, args=(command.task_id, payload, cancelled), daemon=True
            )
            thread.start()
            return self.view(row)

    def revoke(self, ref: TaskRef):
        with self.registry.locked():
            self.registry.write(f"{ref.job_id.hex}.{ref.fence.hex}.revoked", b"revoked\n")
            for row in self.registry.rows():
                if row["job_id"] == str(ref.job_id) and row["fence"] == str(ref.fence):
                    if row["state"] not in TERMINAL:
                        task_id = UUID(row["task_id"])
                        if task_id.hex in self.events:
                            self.events[task_id.hex].set()
                        self.cleanup(row, "cancelled")
            return {"job_id": str(ref.job_id), "fence": str(ref.fence), "revoked": True}

    @staticmethod
    def view(row):
        return {
            key: row[key]
            for key in ("task_id", "job_id", "fence", "state", "cleanup_confirmed", "artifact_hash")
        }

    def read(self, task_id: UUID, ref: TaskRef):
        with self.registry.locked():
            row = self.registry.load(task_id)
            self.authorized(row, ref)
            return self.view(row)

    def heartbeat(self, task_id: UUID, ref: TaskRef):
        with self.registry.locked():
            row = self.registry.load(task_id)
            self.authorized(row, ref)
            if row["state"] in TERMINAL and row["cleanup_confirmed"]:
                return self.view(row)
            at = time.time()
            if (
                row["state"] not in ("accepted", "running")
                or at >= row["lease_until"]
                or (at >= row["deadline_at"] or at < row["last_clock"])
            ):
                raise TaskError("TASK_LEASE_EXPIRED")
            row.update(lease_until=min(at + 30, row["deadline_at"]), last_clock=at)
            self.registry.save(row)
            return self.view(row)

    def cancel(self, task_id: UUID, ref: TaskRef):
        with self.registry.locked():
            row = self.registry.load(task_id)
            self.authorized(row, ref)
            if row["state"] not in TERMINAL:
                row["state"] = "cancelling"
                self.registry.save(row)
                if task_id.hex in self.events:
                    self.events[task_id.hex].set()
                self.cleanup(row, "cancelled")
            return self.view(self.registry.load(task_id))

    def cleanup(self, row, outcome, *, final=False):
        # Called with the cross-process registry lock. Never report cancellation before removal.
        cleaned = cleanup_task(UUID(row["task_id"]).hex, scope="task")
        row.update(
            state=outcome if cleaned and final else "cleanup_pending",
            cleanup_confirmed=cleaned and final,
            artifact_hash=None,
            requested_outcome=row.get("requested_outcome", outcome),
        )
        self.registry.save(row)
        artifact = self.registry.root / (UUID(row["task_id"]).hex + ".artifact")
        artifact.unlink(missing_ok=True)

    def execute(self, task_id: UUID, payload: dict, cancelled: threading.Event):
        try:
            with self.registry.locked():
                row = self.registry.load(task_id)
                if row["state"] != "accepted":
                    self.cleanup(row, row.get("requested_outcome", "interrupted"), final=True)
                    return
                row["state"] = "running"
                self.registry.save(row)
                budget = max(1, min(90, math.floor(row["deadline_at"] - time.time())))
            code, output, timed_out, cleaned = run_task(
                self.settings,
                payload,
                budget,
                task_id.hex,
                scope="task",
                cancel_event=cancelled,
            )
            with self.registry.locked():
                row = self.registry.load(task_id)
                if row["state"] in TERMINAL or row["state"] in ("cancelling", "cleanup_pending"):
                    self.cleanup(row, row.get("requested_outcome", "interrupted"), final=True)
                    return
                if not cleaned or timed_out or code != 0:
                    self.cleanup(row, "timed_out" if timed_out else "failed", final=True)
                    return
                if (
                    time.time() >= row["lease_until"]
                    or time.time() >= row["deadline_at"]
                    or time.time() < row["last_clock"]
                ):
                    self.cleanup(row, "timed_out", final=True)
                    return
                digest = capture_artifact(output, payload)
                self.registry.write(task_id.hex + ".artifact", output)
                row.update(
                    state="succeeded",
                    cleanup_confirmed=True,
                    artifact_hash=digest,
                    completed_at=time.time(),
                )
                self.registry.save(row)
        except Exception:
            with self.registry.locked():
                self.cleanup(self.registry.load(task_id), "failed", final=True)
        finally:
            self.events.pop(task_id.hex, None)

    def sweep(self, *, restart=False):
        with self.registry.locked():
            rows = self.registry.rows()
            now = time.time()
            for row in rows:
                if row["state"] not in TERMINAL and (
                    restart
                    or row["boot_id"] != boot_id()
                    or now >= min(row["lease_until"], row["deadline_at"])
                    or now < row["last_clock"]
                    or row["state"] in ("cancelling", "cleanup_pending")
                ):
                    if UUID(row["task_id"]).hex in self.events:
                        self.events[UUID(row["task_id"]).hex].set()
                    self.cleanup(
                        row,
                        row.get(
                            "requested_outcome",
                            "cancelled" if row["state"] == "cancelling" else "interrupted",
                        ),
                        final=restart,
                    )
            # Enumerate exact supervisor labels only; never trust container-provided names.
            inventory = subprocess.run(
                [
                    "docker",
                    "container",
                    "ls",
                    "--all",
                    "--filter",
                    "label=latch.task",
                    "--format",
                    '{{.Label "latch.task"}}',
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            ).stdout.splitlines()
            admitted = {UUID(row["task_id"]).hex: row for row in self.registry.rows()}
            for task in inventory:
                task_id = UUID(task)
                row = admitted.get(task_id.hex)
                if row is None or row["state"] in TERMINAL:
                    cleanup_task(task_id.hex, scope="task")


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
