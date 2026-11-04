"""Durable Argon2id identity, bounded password work and revocable cookie sessions."""

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import OrderedDict
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from services.api.errors import ApiError
from services.domain.contracts import SessionView, UserView, utc_string

COOKIE = "__Host-latch_session"
IDLE_MS = 2 * 60 * 60 * 1000
ABSOLUTE_MS = 12 * 60 * 60 * 1000
REAUTH_MS = 15 * 60 * 1000
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
PASSWORD_SLOTS = threading.BoundedSemaphore(2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def iso_ms(value: int) -> str:
    from datetime import UTC, datetime

    return utc_string(datetime.fromtimestamp(value / 1000, UTC))


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.]{2,63}", value):
        raise ValueError(
            "Username must contain 3 to 64 simple letters, numbers, dots or underscores"
        )
    return value


class RateLimiter:
    "Bounded process-local throttle; deploy one API process until a shared limiter exists."

    def __init__(self):
        self.lock = threading.Lock()
        self.entries: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def check(self, key: str, *, limit: int = 10, seconds: int = 300) -> None:
        now = time.monotonic()
        with self.lock:
            start, count = self.entries.pop(key, (now, 0))
            if now - start >= seconds:
                start, count = now, 0
            self.entries[key] = (start, count + 1)
            while len(self.entries) > 10000:
                self.entries.popitem(last=False)
            if count >= limit:
                raise ApiError(429, "RATE_LIMIT", "error.rate")


def verify_password(encoded: str, password: str) -> bool:
    if not PASSWORD_SLOTS.acquire(blocking=False):
        raise ApiError(429, "RATE_LIMIT", "error.rate")
    try:
        try:
            return HASHER.verify(encoded, password)
        except VerificationError:
            return False
    finally:
        PASSWORD_SLOTS.release()


def provision_user(conn, username: str, display_name: str, password: str) -> str:
    username = normalize_username(username)
    if not 12 <= len(password) <= 256 or not 1 <= len(display_name.strip()) <= 100:
        raise ValueError("Use a 12 to 256 character password and a display name")
    user_id, at = str(uuid4()), now_ms()
    conn.execute(
        "INSERT INTO users VALUES (%s,%s,%s,%s,true,%s,%s)",
        (user_id, username, display_name.strip(), HASHER.hash(password), at, at),
    )
    return user_id


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def user_view(row) -> UserView:
    return UserView(
        id=str(row["user_id"]), username=row["username"], display_name=row["display_name"]
    )


def session_row(conn, token: str | None, *, lock: bool = False):
    if token is None or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise ApiError(401, "SESSION_REQUIRED", "error.session")
    row = conn.execute(
        (
            "SELECT s.*,u.username,u.display_name,u.active FROM sessions s JOIN "
            "users u ON u.id=s.user_id WHERE s.token_hash=%s"
        )
        + (" FOR UPDATE OF s,u" if lock else ""),
        (token_hash(token),),
    ).fetchone()
    at = now_ms()
    if (
        row is None
        or not row["active"]
        or row["revoked_at"] is not None
        or at >= row["absolute_expires_at"]
        or at - row["last_seen_at"] >= IDLE_MS
        or at < row["created_at"]
    ):
        raise ApiError(401, "SESSION_REQUIRED", "error.session")
    # Update at most once per minute; lock if mutating to prevent logout/command races.
    if at - row["last_seen_at"] >= 60000:
        conn.execute(
            (
                "UPDATE sessions SET last_seen_at=GREATEST(last_seen_at,%s) WHERE "
                "id=%s AND revoked_at IS NULL"
            ),
            (at, row["id"]),
        )
        row["last_seen_at"] = at
    return row


def new_session(conn, user_id, *, absolute_expires_at: int | None = None) -> str:
    at, token = now_ms(), secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions VALUES(%s,%s,%s,%s,%s,%s,%s,NULL)",
        (uuid4(), token_hash(token), user_id, at, at, absolute_expires_at or at + ABSOLUTE_MS, at),
    )
    return token


def csrf(secret: str, token: str) -> str:
    return hmac.new(secret.encode(), ("csrf-v1:" + token).encode(), hashlib.sha256).hexdigest()


def session_view(row, token: str, secret: str) -> SessionView:
    return SessionView(
        user=user_view(row),
        csrf_token=csrf(secret, token),
        expires_at=iso_ms(min(row["absolute_expires_at"], row["last_seen_at"] + IDLE_MS)),
        reauth_fresh=0 <= now_ms() - row["reauthenticated_at"] < REAUTH_MS,
    )
