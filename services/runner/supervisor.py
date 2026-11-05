"""Trusted fixed-command mTLS client. No redirects, ambient proxies or unbounded artifacts."""

import hashlib
import json
import ssl
from pathlib import Path
from uuid import UUID

import httpx

from services.common.task_contracts import TaskCommand, TaskRef


class SupervisorUnavailable(RuntimeError):
    pass


class SupervisorRejected(SupervisorUnavailable):
    pass


class SupervisorClient:
    def __init__(self, tls: Path, *, port=9443):
        context = ssl.create_default_context(cafile=tls / "ca.crt")
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(tls / "runner.crt", tls / "runner.key")
        self.client = httpx.Client(
            base_url=f"https://127.0.0.1:{port}",
            verify=context,
            timeout=10,
            follow_redirects=False,
            trust_env=False,
        )

    def close(self):
        self.client.close()

    def request(self, path, command):
        try:
            with self.client.stream("POST", path, json=command.model_dump(mode="json")) as response:
                data = bytearray()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > 16 * 1024:
                        raise SupervisorUnavailable("SUPERVISOR_RESPONSE_LIMIT")
                    data.extend(chunk)
                value = json.loads(data)
                if response.status_code not in (200, 202):
                    code = value.get("code", "SUPERVISOR_COMMAND_REJECTED")
                    if (
                        not isinstance(code, str)
                        or len(code) > 100
                        or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_" for c in code)
                    ):
                        code = "SUPERVISOR_COMMAND_REJECTED"
                    raise SupervisorRejected(code)
                if value["job_id"] != str(command.job_id) or value["fence"] != str(command.fence):
                    raise SupervisorUnavailable("SUPERVISOR_FENCE_MISMATCH")
                return value
        except (httpx.HTTPError, ValueError, KeyError) as error:
            raise SupervisorUnavailable("SUPERVISOR_UNAVAILABLE") from error

    def submit(self, command: TaskCommand):
        result = self.request("/v1/tasks", command)
        if result["task_id"] != str(command.task_id):
            raise SupervisorUnavailable("SUPERVISOR_TASK_MISMATCH")
        return result

    def revoke(self, ref: TaskRef):
        return self.request("/v1/fences/revoke", ref)

    def action(self, task_id: UUID, ref: TaskRef, action: str):
        if action not in ("status", "heartbeat", "cancel"):
            raise ValueError("INVALID_SUPERVISOR_ACTION")
        result = self.request(f"/v1/tasks/{task_id}/{action}", ref)
        if result["task_id"] != str(task_id):
            raise SupervisorUnavailable("SUPERVISOR_TASK_MISMATCH")
        return result

    def artifact(self, task_id: UUID, ref: TaskRef, target: Path, expected_hash: str):
        temporary = target.with_suffix(".partial")
        try:
            with self.client.stream(
                "POST", f"/v1/tasks/{task_id}/artifact", json=ref.model_dump(mode="json")
            ) as response:
                if response.status_code != 200:
                    raise SupervisorUnavailable("SUPERVISOR_ARTIFACT_UNAVAILABLE")
                total, digest = 0, hashlib.sha256()
                with temporary.open("xb") as out:
                    temporary.chmod(0o600)
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > 15 * 1024 * 1024:
                            raise SupervisorUnavailable("SUPERVISOR_ARTIFACT_LIMIT")
                        digest.update(chunk)
                        out.write(chunk)
                if (
                    digest.hexdigest() != expected_hash
                    or response.headers.get("x-content-sha256") != expected_hash
                ):
                    raise SupervisorUnavailable("SUPERVISOR_ARTIFACT_HASH")
                temporary.replace(target)
        except httpx.HTTPError as error:
            raise SupervisorUnavailable("SUPERVISOR_UNAVAILABLE") from error
        finally:
            temporary.unlink(missing_ok=True)
