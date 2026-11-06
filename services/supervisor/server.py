"""Private mTLS supervisor; loopback binding requires the pinned operator SSH tunnel."""

import argparse
import hashlib
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

from services.common.source_policy import SourceProfile, profile_hash
from services.common.task_contracts import TaskCommand, TaskRef
from services.supervisor.spike import WorkerSettings, host_preflight
from services.supervisor.tasks import Registry, TaskError, Tasks


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, context, tasks):
        self.context, self.tasks = context, tasks
        self.slots = threading.BoundedSemaphore(12)
        super().__init__(address, Handler)

    def get_request(self):
        connection, address = self.socket.accept()
        connection.settimeout(5)
        # Handshake in handler threads so an incomplete TLS client cannot stall all requests.
        return self.context.wrap_socket(
            connection, server_side=True, do_handshake_on_connect=False
        ), address

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            request.do_handshake()
            certificate = request.getpeercert()
            if ("URI", "urn:latch:runner") not in certificate.get("subjectAltName", ()):
                return
            super().process_request_thread(request, address)
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
        finally:
            self.shutdown_request(request)
            self.slots.release()

    def handle_error(self, request, address):
        # Never log request bodies, certificate contents, URLs, paths or worker data.
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def dispatch(self):
        try:
            if (
                self.headers.get("Transfer-Encoding")
                or len(self.headers.get_all("Content-Length", [])) != 1
            ):
                raise TaskError("BODY_FRAMING")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= 16 * 1024:
                raise TaskError("BODY_LIMIT")
            if self.headers.get("Content-Type") != "application/json":
                raise TaskError("JSON_REQUIRED")
            body = self.rfile.read(length)
            if len(body) != length:
                raise TaskError("BODY_TRUNCATED")
            tasks = self.server.tasks
            if self.path == "/v1/fences/revoke" and self.command == "POST":
                return self.reply(200, tasks.revoke(TaskRef.model_validate_json(body)))
            if self.path == "/v1/tasks" and self.command == "POST":
                return self.reply(202, tasks.submit(TaskCommand.model_validate_json(body)))
            parts = self.path.split("/")
            if len(parts) != 5 or parts[:3] != ["", "v1", "tasks"]:
                raise TaskError("ROUTE_NOT_FOUND")
            task_id, action = UUID(parts[3]), parts[4]
            ref = TaskRef.model_validate_json(body)
            # All operations use POST; a credential or fence never goes in the URL/query/log.
            if self.command != "POST":
                raise TaskError("METHOD_REJECTED")
            if action == "status":
                return self.reply(200, tasks.read(task_id, ref))
            if action == "heartbeat":
                return self.reply(200, tasks.heartbeat(task_id, ref))
            if action == "cancel":
                return self.reply(202, tasks.cancel(task_id, ref))
            if action == "artifact":
                with tasks.registry.locked():
                    row = tasks.registry.load(task_id)
                    tasks.authorized(row, ref)
                    if row["state"] != "succeeded" or not row["cleanup_confirmed"]:
                        raise TaskError("ARTIFACT_NOT_READY")
                    data = (tasks.registry.root / (task_id.hex + ".artifact")).read_bytes()
                    if (
                        len(data) > 15 * 1024 * 1024
                        or hashlib.sha256(data).hexdigest() != row["artifact_hash"]
                    ):
                        raise TaskError("ARTIFACT_HASH")
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-SHA256", row["artifact_hash"])
                self.end_headers()
                self.wfile.write(data)
                return
            raise TaskError("ROUTE_NOT_FOUND")
        except TaskError as error:
            self.reply(409, {"code": str(error)})
        except (ValueError, KeyError, TypeError):
            self.reply(422, {"code": "INVALID_COMMAND"})
        except (OSError, RuntimeError):
            self.reply(503, {"code": "SUPERVISOR_UNAVAILABLE"})

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    do_POST = dispatch

    def do_GET(self):
        if self.path != "/v1/health" or self.headers.get("Transfer-Encoding"):
            return self.reply(404, {"code": "ROUTE_NOT_FOUND"})
        return self.reply(200, {
            "status": "ready",
            "profiles": [{"id": p.id, "version": p.version, "hash": profile_hash(p)}
                         for p in self.server.tasks.profiles.values()],
        })


def load(args):
    if args.config.stat().st_size > 64 * 1024:
        raise TaskError("CONFIG_LIMIT")
    value = json.loads(args.config.read_bytes())
    if set(value) != {"worker", "profiles"} or not 1 <= len(value["profiles"]) <= 10:
        raise TaskError("CONFIG_SCHEMA")
    return Tasks(
        Registry(args.state),
        WorkerSettings.model_validate(value["worker"]),
        [SourceProfile.model_validate(p) for p in value["profiles"]],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--tls", type=Path)
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    tasks = load(args)
    if args.sweep:
        tasks.sweep()
        return
    if not args.tls:
        parser.error("--tls is required for server")
    host_preflight(tasks.settings)
    tasks.sweep(restart=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(args.tls / "ca.crt")
    context.load_cert_chain(args.tls / "server.crt", args.tls / "server.key")
    with Server(("127.0.0.1", 9443), context, tasks) as server:
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
