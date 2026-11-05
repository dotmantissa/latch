"""External, bounded HTTPS inspection proxy. Browser requests never become host commands."""

import argparse
import hashlib
import http.client
import json
import socket
import socketserver
import ssl
import string
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from services.common.urls import public_https_url, require_public_addresses

HEADER_LIMIT = 16 * 1024
BODY_LIMIT = 8 * 1024 * 1024
ASSET_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
                  ".ico", ".woff", ".woff2", ".ttf")


class Denied(ValueError):
    pass


class EgressPolicy:
    def __init__(self, value: dict):
        if set(value) != {"pages", "asset_origins", "expires_at"}:
            raise Denied("POLICY_SCHEMA")
        if not isinstance(value["pages"], list) or not 1 <= len(value["pages"]) <= 6:
            raise Denied("POLICY_PAGE_LIMIT")
        if not isinstance(value["asset_origins"], list) or len(value["asset_origins"]) > 10:
            raise Denied("POLICY_ASSET_LIMIT")
        self.pages = frozenset(public_https_url(url) for url in value["pages"])
        self.assets = frozenset(public_https_url(url).rstrip("/")
                                for url in value["asset_origins"])
        if any(urlsplit(origin).path for origin in self.assets):
            raise Denied("ASSET_ORIGIN_REQUIRED")
        self.expires_at = datetime.fromisoformat(value["expires_at"])
        if self.expires_at.tzinfo is None:
            raise Denied("POLICY_TIMEZONE")
        self.hosts = frozenset(urlsplit(url).hostname for url in self.pages | self.assets)
        self.active()

    def active(self) -> None:
        if datetime.now(UTC) >= self.expires_at:
            raise Denied("POLICY_EXPIRED")

    def connect_host(self, authority: str) -> str:
        self.active()
        if not authority.endswith(":443") or authority.count(":") != 1:
            raise Denied("CONNECT_PORT")
        host = authority[:-4]
        if host not in self.hosts:
            raise Denied("CONNECT_HOST")
        return host

    def request(self, host: str, method: str, target: str, headers: dict) -> str:
        self.active()
        if method not in ("GET", "HEAD") or not target.startswith("/") or target.startswith("//"):
            raise Denied("REQUEST_METHOD_OR_TARGET")
        if headers.get("host") not in (host, host + ":443"):
            raise Denied("REQUEST_HOST")
        if any(name in headers for name in ("authorization", "proxy-authorization", "cookie",
                                             "transfer-encoding", "upgrade")):
            raise Denied("REQUEST_AUTH_OR_BODY")
        if headers.get("content-length", "0") != "0":
            raise Denied("REQUEST_BODY")
        try:
            url = public_https_url("https://" + host + target)
        except ValueError as error:
            raise Denied("REQUEST_URL") from error
        if url in self.pages:
            return url
        origin = "https://" + host
        if (origin in self.assets and target.lower().endswith(ASSET_SUFFIXES)
                and headers.get("sec-fetch-dest") not in ("document", "iframe", "frame")):
            return url
        raise Denied("REQUEST_PATH")


def parse_headers(raw: bytes) -> tuple[str, str, dict]:
    """Reject ambiguity before any TLS or public destination socket is opened."""
    if len(raw) > HEADER_LIMIT or not raw.endswith(b"\r\n\r\n"):
        raise Denied("HEADER_LIMIT")
    try:
        lines = raw.decode("ascii").split("\r\n")
    except UnicodeError as error:
        raise Denied("HEADER_ENCODING") from error
    parts = lines[0].split(" ")
    if len(parts) != 3 or parts[2] != "HTTP/1.1" or len(lines[0]) > 2200:
        raise Denied("REQUEST_LINE")
    headers = {}
    for line in lines[1:-2]:
        if not line or line.startswith((" ", "\t")) or ":" not in line:
            raise Denied("HEADER_SYNTAX")
        name, value = line.split(":", 1)
        if not name or any(c not in string.ascii_letters + string.digits + "-" for c in name):
            raise Denied("HEADER_NAME")
        name = name.lower()
        if name in headers or any((ord(c) < 32 and c != "\t") or ord(c) == 127 for c in value):
            raise Denied("HEADER_DUPLICATE_OR_CONTROL")
        headers[name] = value.strip()
    return parts[0], parts[1], headers


def read_headers(stream) -> bytes:
    data = bytearray()
    while not data.endswith(b"\r\n\r\n"):
        line = stream.readline(HEADER_LIMIT + 1)
        if not line:
            raise Denied("HEADER_EOF")
        data.extend(line)
        if len(data) > HEADER_LIMIT:
            raise Denied("HEADER_LIMIT")
    return bytes(data)


def event(kind: str, reason: str, host: str | None = None, target: str = "") -> None:
    print(json.dumps({
        "at": datetime.now(UTC).isoformat(), "event": kind, "reason": reason,
        "host": host, "path_sha256": hashlib.sha256(target.encode()).hexdigest(),
    }), flush=True)


def public_socket(host: str, deadline: float):
    if deadline <= time.monotonic():
        raise Denied("CONNECTION_DEADLINE")
    answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = require_public_addresses([answer[4][0] for answer in answers])
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["http/1.1"])
    for address in dict.fromkeys(addresses):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Denied("CONNECTION_DEADLINE")
        connection = None
        try:
            # Connect to the reviewed numeric answer, preserving DNS hostname for TLS verification.
            connection = socket.create_connection((address, 443), timeout=min(8, remaining))
            return context.wrap_socket(connection, server_hostname=host)
        except OSError:
            if connection is not None:
                connection.close()
    raise Denied("UPSTREAM_UNAVAILABLE")


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        host = None
        target = ""
        connection = self.request
        connection.settimeout(10)
        deadline = time.monotonic() + 90
        active_sockets = [connection]

        def expire():
            for active in active_sockets.copy():
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        watchdog = threading.Timer(90, expire)
        watchdog.daemon = True
        watchdog.start()
        try:
            # An unbuffered stream cannot consume bytes belonging to the following TLS handshake.
            with connection.makefile("rb", buffering=0) as stream:
                method, authority, headers = parse_headers(read_headers(stream))
                target = authority
            if method != "CONNECT" or any(name in headers for name in (
                    "authorization", "proxy-authorization", "transfer-encoding")):
                raise Denied("CONNECT_REQUIRED")
            if headers.get("content-length", "0") != "0":
                raise Denied("CONNECT_BODY")
            host = self.server.policy.connect_host(authority)
            connection.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            connection = self.server.contexts[host].wrap_socket(connection, server_side=True)
            active_sockets.append(connection)
            connection.settimeout(10)
            with connection.makefile("rb") as stream:
                for _ in range(32):
                    method, target, headers = parse_headers(read_headers(stream))
                    self.server.policy.request(host, method, target, headers)
                    with public_socket(host, deadline) as upstream:
                        active_sockets.append(upstream)
                        forwarded = [f"{method} {target} HTTP/1.1", f"Host: {host}",
                                     "Connection: close", "Accept-Encoding: identity"]
                        for name in ("accept", "accept-language", "user-agent"):
                            if name in headers:
                                forwarded.append(f"{name}: {headers[name]}")
                        upstream.sendall(("\r\n".join(forwarded) + "\r\n\r\n").encode())
                        response = http.client.HTTPResponse(upstream, method=method)
                        response.begin()
                        if response.getheader("Content-Encoding", "identity") != "identity":
                            raise Denied("UPSTREAM_ENCODING")
                        if 300 <= response.status < 400:
                            raise Denied("UPSTREAM_REDIRECT")
                        body = response.read(BODY_LIMIT + 1)
                        if len(body) > BODY_LIMIT:
                            raise Denied("UPSTREAM_BODY_LIMIT")
                        content_type = response.getheader(
                            "Content-Type", "application/octet-stream"
                        )
                        if any(ord(c) < 32 or ord(c) > 126 for c in content_type):
                            raise Denied("UPSTREAM_HEADER")
                        output = (
                            f"HTTP/1.1 {response.status} Response\r\n"
                            f"Content-Type: {content_type}\r\n"
                            f"Content-Length: {len(body)}\r\n"
                            "Cache-Control: no-store\r\nConnection: keep-alive\r\n\r\n"
                        ).encode() + body
                        connection.sendall(output)
                        event("upstream_response", str(response.status), host, target)
                    active_sockets.remove(upstream)
                    if headers.get("connection", "").lower() == "close":
                        break
        except (OSError, ValueError, http.client.HTTPException) as error:
            reason = str(error) if isinstance(error, Denied) else type(error).__name__
            event("denied", reason, host, target)
            try:
                connection.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n"
                                   b"Connection: close\r\n\r\n")
            except OSError:
                pass
        finally:
            watchdog.cancel()
            connection.close()


class ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple, policy: EgressPolicy, tls_dir: Path):
        self.policy = policy
        self.contexts = {}
        self.slots = threading.BoundedSemaphore(16)
        for host in policy.hosts:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.set_alpn_protocols(["http/1.1"])
            context.load_cert_chain(tls_dir / (host + ".chain.crt"), tls_dir / (host + ".key"))

            def check_sni(connection, name, original, expected=host):
                if name != expected:
                    raise ssl.SSLError("Unreviewed TLS server name")

            context.set_servername_callback(check_sni)
            self.contexts[host] = context
        super().__init__(address, ProxyHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-file", required=True, type=Path)
    parser.add_argument("--tls-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.policy_file.stat().st_size > 32 * 1024:
        raise Denied("POLICY_SIZE")
    policy = EgressPolicy(json.loads(args.policy_file.read_text()))
    with ProxyServer(("172.29.240.1", 3128), policy, args.tls_dir) as server:
        event("ready", "REVIEWED_POLICY")
        server.serve_forever()


if __name__ == "__main__":
    main()
