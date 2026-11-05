"""Provider-independent API and same-origin application delivery."""

import asyncio
import hmac
import json
import re
import time
from contextlib import asynccontextmanager, contextmanager
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from anyio import to_thread
from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from services.api.auth import (
    COOKIE,
    DUMMY_HASH,
    RateLimiter,
    csrf,
    iso_ms,
    new_session,
    normalize_username,
    now_ms,
    session_row,
    session_view,
    verify_password,
)
from services.api.errors import ApiError
from services.api.settings import AppSettings
from services.artifacts.contracts import CaptureView
from services.artifacts.sanitize import POLICY_VERSION, ArtifactRejected, dimensions
from services.artifacts.store import ArtifactStore
from services.common.config import read_secret
from services.common.source_policy import StrictRecord
from services.domain.contracts import (
    ErrorView,
    JobView,
    ProfileView,
    RequestInput,
    RequestPage,
    RequestView,
    SessionView,
    utc_string,
)
from services.storage import evidence, jobs
from services.storage import requests as store
from services.storage.database import database


class Envelope[T](BaseModel):
    data: T
    resource_version: int | None = None


class LoginInput(StrictRecord):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordInput(StrictRecord):
    password: str = Field(min_length=1, max_length=256)


class VersionInput(StrictRecord):
    current_version: int = Field(strict=True, ge=1)


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 2 * 1024 * 1024:
                response = JSONResponse(
                    ErrorView(
                        code="BODY_TOO_LARGE",
                        message_key="error.large",
                        correlation_id=str(uuid4()),
                    ).model_dump(),
                    status_code=413,
                    headers={"Cache-Control": "no-store"},
                )
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def bounded_receive():
            return messages.pop(0) if messages else await receive()

        await self.app(scope, bounded_receive, send)


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or AppSettings.from_environment()
    url, secret = settings.database_url(), read_secret(settings.csrf_key_file)
    limiter = RateLimiter()
    streams: dict[str, int] = {}

    @asynccontextmanager
    async def lifespan(app):
        with database(url, schema=settings.database_schema):
            pass
        yield

    app = FastAPI(
        title="Latch",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(BodyLimit)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.public_origin).hostname]
    )

    def failure(error: ApiError, correlation: str):
        return JSONResponse(
            ErrorView(
                code=error.code,
                message_key=error.message_key,
                field_errors=error.fields,
                retryable=error.status in (429, 503),
                correlation_id=correlation,
                current_version=error.current_version,
            ).model_dump(),
            status_code=error.status,
        )

    @app.exception_handler(ApiError)
    async def safe_error(request: Request, error: ApiError):
        return failure(error, request.state.correlation)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        fields = {
            ".".join(str(part) for part in item["loc"][1:]): "error.field"
            for item in error.errors()
        }
        return failure(
            ApiError(422, "VALIDATION_ERROR", "error.field", fields=fields),
            request.state.correlation,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception):
        return failure(ApiError(500, "INTERNAL_ERROR"), request.state.correlation)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request.state.correlation = str(uuid4())
        try:
            if request.url.path.startswith("/api/"):
                accepted = request.headers.get("accept", "*/*")
                formats = ("application/json", "*/*")
                if request.url.path.endswith("/events") and request.method == "GET":
                    formats += ("text/event-stream",)
                if request.url.path.startswith("/api/v1/artifacts/") and request.method == "GET":
                    formats += ("image/png",)
                if not any(kind in accepted for kind in formats):
                    raise ApiError(406, "JSON_REQUIRED", "error.format")
                if request.method in ("POST", "PATCH", "DELETE", "PUT"):
                    if request.headers.get("origin") != settings.public_origin:
                        raise ApiError(403, "CSRF_ORIGIN_REJECTED", "error.origin")
                    if (
                        request.headers.get("content-type", "").split(";")[0].strip()
                        != "application/json"
                    ):
                        raise ApiError(415, "JSON_REQUIRED", "error.format")
            response = await call_next(request)
        except ApiError as error:
            response = failure(error, request.state.correlation)
        except psycopg.Error:
            response = failure(
                ApiError(503, "DATABASE_UNAVAILABLE", "error.database"), request.state.correlation
            )
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; img-src "
                    "'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors "
                    "'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
                ),
                "X-Request-ID": request.state.correlation,
            }
        )
        return response

    @contextmanager
    def authorized(request: Request):
        with database(url, schema=settings.database_schema) as conn:
            mutation = request.method not in ("GET", "HEAD")
            token = request.cookies.get(COOKIE)
            row = session_row(conn, token, lock=mutation)
            if mutation and not hmac.compare_digest(
                request.headers.get("x-csrf-token", ""), csrf(secret, token)
            ):
                raise ApiError(403, "CSRF_ORIGIN_REJECTED", "error.origin")
            yield conn, row

    def key(request: Request) -> str:
        value = request.headers.get("idempotency-key", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,128}", value):
            raise ApiError(422, "IDEMPOTENCY_REQUIRED", "error.idempotency")
        return value

    def expected(request: Request) -> int:
        value = request.headers.get("if-match", "")
        if not re.fullmatch(r'"[1-9][0-9]{0,8}"', value):
            raise ApiError(428, "VERSION_PRECONDITION_REQUIRED", "error.conflict")
        return int(value[1:-1])

    def cookie(response: Response, token: str):
        response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="lax", path="/")

    @app.get("/health/live")
    def live():
        return {"status": "healthy"}

    @app.get("/health/ready")
    def ready():
        try:
            with database(url, schema=settings.database_schema):
                pass
            return {"status": "degraded"}
        except (psycopg.Error, RuntimeError):
            return JSONResponse({"status": "unavailable"}, status_code=503)

    @app.post("/api/v1/auth/login", response_model=Envelope[SessionView])
    def login(body: LoginInput, request: Request, response: Response):
        address = request.client.host if request.client else "unknown"
        limiter.check(f"ip:{address}", limit=30)
        limiter.check(f"account:{body.username.strip().lower()}")
        try:
            username = normalize_username(body.username)
        except ValueError:
            username = ""
        with database(url, schema=settings.database_schema) as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username=%s FOR UPDATE", (username,)
            ).fetchone()
            valid = verify_password(user["password_hash"] if user else DUMMY_HASH, body.password)
            if not valid or not user or not user["active"]:
                raise ApiError(401, "LOGIN_FAILED", "error.login")
            # Rotate an existing browser session, preserving other independent sessions.
            prior = request.cookies.get(COOKIE)
            if prior:
                from services.api.auth import token_hash

                conn.execute(
                    "UPDATE sessions SET revoked_at=%s WHERE token_hash=%s",
                    (now_ms(), token_hash(prior)),
                )
            token = new_session(conn, user["id"])
            result = session_view(session_row(conn, token), token, secret)
        cookie(response, token)
        return Envelope(data=result)

    @app.get("/api/v1/auth/session", response_model=Envelope[SessionView])
    def session(request: Request):
        with authorized(request) as (_, row):
            return Envelope(data=session_view(row, request.cookies[COOKIE], secret))

    @app.post("/api/v1/auth/reauth", response_model=Envelope[SessionView])
    def reauth(body: PasswordInput, request: Request, response: Response):
        with authorized(request) as (conn, row):
            limiter.check(f"reauth:{row['user_id']}")
            encoded = conn.execute(
                "SELECT password_hash FROM users WHERE id=%s", (row["user_id"],)
            ).fetchone()["password_hash"]
            if not verify_password(encoded, body.password):
                raise ApiError(401, "LOGIN_FAILED", "error.login")
            conn.execute("UPDATE sessions SET revoked_at=%s WHERE id=%s", (now_ms(), row["id"]))
            token = new_session(
                conn, row["user_id"], absolute_expires_at=row["absolute_expires_at"]
            )
            result = session_view(session_row(conn, token), token, secret)
        cookie(response, token)
        return Envelope(data=result)

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(request: Request):
        with authorized(request) as (conn, row):
            conn.execute("UPDATE sessions SET revoked_at=%s WHERE id=%s", (now_ms(), row["id"]))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return response

    @app.get("/api/v1/source-profiles", response_model=Envelope[list[ProfileView]])
    def source_profiles(request: Request):
        with authorized(request) as (conn, _):
            return Envelope(
                data=[
                    ProfileView(
                        id=p.id,
                        version=p.version,
                        origin=p.origin,
                        offer_paths=p.offer_paths,
                        expires_at=utc_string(p.expires_at),
                    )
                    for p in store.profiles(conn)
                ]
            )

    @app.get("/api/v1/requests", response_model=Envelope[RequestPage])
    def requests(
        request: Request,
        cursor: int | None = Query(None, ge=1),
        limit: int = Query(50, ge=1, le=50),
    ):
        with authorized(request) as (conn, row):
            return Envelope(data=store.listing(conn, row["user_id"], cursor, limit))

    @app.post("/api/v1/requests", status_code=201, response_model=Envelope[RequestView])
    def create(body: RequestInput, request: Request, response: Response):
        with authorized(request) as (conn, row):
            limiter.check(f"save:{row['user_id']}", limit=60, seconds=60)
            result = store.save(conn, row["user_id"], body, key(request))
        response.headers["ETag"] = f'"{result.version}"'
        return Envelope(data=result, resource_version=result.version)

    @app.get("/api/v1/requests/{request_id}", response_model=Envelope[RequestView])
    def detail(
        request_id: UUID,
        request: Request,
        response: Response,
        version: int | None = Query(None, ge=1),
    ):
        with authorized(request) as (conn, row):
            result = store.view(conn, row["user_id"], request_id, version)
        response.headers["ETag"] = f'"{result.version}"'
        return Envelope(data=result, resource_version=result.version)

    @app.get("/api/v1/requests/{request_id}/history", response_model=Envelope[list[int]])
    def history(request_id: UUID, request: Request):
        with authorized(request) as (conn, row):
            store.owned(conn, row["user_id"], request_id)
            versions = conn.execute(
                "SELECT version FROM request_versions WHERE request_id=%s ORDER BY version DESC",
                (request_id,),
            ).fetchall()
            return Envelope(data=[item["version"] for item in versions])

    @app.patch("/api/v1/requests/{request_id}", response_model=Envelope[RequestView])
    def edit(request_id: UUID, body: RequestInput, request: Request, response: Response):
        with authorized(request) as (conn, row):
            result = store.save(
                conn,
                row["user_id"],
                body,
                key(request),
                request_id=request_id,
                expected=expected(request),
            )
        response.headers["ETag"] = f'"{result.version}"'
        return Envelope(data=result, resource_version=result.version)

    @app.post("/api/v1/requests/{request_id}/archive", response_model=Envelope[RequestView])
    def archive(request_id: UUID, body: VersionInput, request: Request):
        if expected(request) != body.current_version:
            raise ApiError(412, "VERSION_PRECONDITION", "error.conflict")
        with authorized(request) as (conn, row):
            result = store.archive(conn, row["user_id"], request_id, body.current_version)
            return Envelope(data=result, resource_version=result.version)

    @app.get("/api/v1/requests/{request_id}/evidence", response_model=Envelope[list[CaptureView]])
    def captured_evidence(
        request_id: UUID, request: Request, version: int | None = Query(None, ge=1),
    ):
        with authorized(request) as (conn, row):
            saved = store.view(conn, row["user_id"], request_id, version)
            result = evidence.views(conn, row["user_id"], request_id, saved.version)
        return Envelope(data=result, resource_version=saved.version)

    @app.get("/api/v1/artifacts/{artifact_id}", response_class=Response,
             responses={200: {"content": {"image/png": {}}}})
    def captured_artifact(artifact_id: UUID, request: Request):
        with authorized(request) as (conn, row):
            record = evidence.artifact(conn, row["user_id"], artifact_id)
        try:
            if record["sanitizer_version"] != POLICY_VERSION:
                raise ArtifactRejected("ARTIFACT_POLICY_UNSUPPORTED")
            with ArtifactStore(settings.evidence_dir) as files:
                value = files.read(record["sanitized_png_hash"], size=record["sanitized_bytes"])
            if dimensions(value) != (record["width"], record["height"]):
                raise ArtifactRejected("ARTIFACT_DIMENSIONS_MISMATCH")
        except (ArtifactRejected, OSError):
            raise ApiError(503, "ARTIFACT_UNAVAILABLE") from None
        return Response(value, media_type="image/png", headers={
            "Content-Disposition": f'inline; filename="{artifact_id}.png"',
            "Cross-Origin-Resource-Policy": "same-origin",
        })

    @app.post("/api/v1/requests/{request_id}/inspections")
    def inspect(request_id: UUID, body: VersionInput, request: Request):
        with authorized(request) as (conn, row):
            store.owned(conn, row["user_id"], request_id)
            raise ApiError(503, "WORKER_UNAVAILABLE", "error.worker")

    def job_view(row):
        return JobView(
            id=str(row["id"]),
            request_id=str(row["request_id"]),
            request_version=row["request_version"],
            state=row["state"],
            attempt=row["attempt"],
            created_at=iso_ms(row["created_at"]),
            finished_at=iso_ms(row["finished_at"]) if row["finished_at"] else None,
            failure_code=row["failure_code"],
        )

    @app.get("/api/v1/jobs/{job_id}", response_model=Envelope[JobView])
    def job_status(job_id: UUID, request: Request):
        with authorized(request) as (conn, row):
            return Envelope(data=job_view(jobs.get(conn, row["user_id"], job_id)))

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=Envelope[JobView])
    def job_cancel(job_id: UUID, request: Request):
        with authorized(request) as (conn, row):
            return Envelope(data=job_view(jobs.cancel(conn, row["user_id"], job_id)))

    @app.get(
        "/api/v1/jobs/{job_id}/events",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {}}}},
    )
    async def job_events(job_id: UUID, request: Request):
        last = request.headers.get("last-event-id", "0")
        if not re.fullmatch(r"[0-9]{1,19}", last) or int(last) > 9223372036854775807:
            raise ApiError(422, "INVALID_EVENT_CURSOR", "error.field")

        def replay(cursor):
            # Reauthorize every replay, including session expiry/revocation during a stream.
            with authorized(request) as (conn, user):
                job = jobs.get(conn, user["user_id"], job_id)
                rows = conn.execute(
                    "SELECT id,safe_payload_json FROM events WHERE owner_id=%s "
                    "AND job_id=%s AND id>%s ORDER BY id LIMIT 100",
                    (user["user_id"], job_id, cursor),
                ).fetchall()
                return job, rows

        initial = await to_thread.run_sync(replay, int(last))
        owner = str(initial[0]["owner_id"])
        # This accounting stays on the single ASGI event loop; no await between check/increment.
        if streams.get(owner, 0) >= 3 or sum(streams.values()) >= 32:
            raise ApiError(429, "EVENT_STREAM_LIMIT", "error.generic")
        streams[owner] = streams.get(owner, 0) + 1

        async def stream():
            cursor, batch, ping = int(last), initial, time.monotonic()
            yield ": connected\n\n"
            while not await request.is_disconnected():
                job, rows = batch
                for item in rows:
                    cursor = item["id"]
                    yield (
                        f"id: {cursor}\nevent: status\ndata: "
                        + json.dumps(item["safe_payload_json"], separators=(",", ":"))
                        + "\n\n"
                    )
                if job["state"] in jobs.TERMINAL and len(rows) < 100:
                    return
                if time.monotonic() - ping >= 15:
                    yield ": heartbeat\n\n"
                    ping = time.monotonic()
                await asyncio.sleep(1)
                try:
                    batch = await to_thread.run_sync(replay, cursor)
                except (ApiError, psycopg.Error, RuntimeError):
                    return

        async def bounded_stream():
            try:
                async for message in stream():
                    yield message
            finally:
                streams[owner] -= 1
                if not streams[owner]:
                    del streams[owner]

        return StreamingResponse(
            bounded_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # Generated contracts are built from this actual app; no infrastructure schemas are exposed.
    if settings.static_dir.is_dir():
        for folder in ("assets", "brand", "icons", "fonts"):
            directory = settings.static_dir / folder
            if directory.is_dir():
                app.mount(f"/{folder}", StaticFiles(directory=directory), name=folder)

    @app.get("/theme.js", include_in_schema=False)
    def theme_script():
        return FileResponse(settings.static_dir / "theme.js", media_type="text/javascript")

    @app.get("/{path:path}", include_in_schema=False)
    def shell(path: str):
        if path.startswith(("api/", "health/")) or "." in path:
            raise ApiError(404, "NOT_FOUND", "error.notFound")
        index = settings.static_dir / "index.html"
        if not index.is_file():
            raise ApiError(503, "APP_NOT_BUILT", "error.generic")
        return FileResponse(index)

    return app
