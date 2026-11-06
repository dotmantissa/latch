"""Real HTTP commands backed by an isolated schema on the supplied Neon database."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.auth import COOKIE, IDLE_MS, now_ms, provision_user
from services.api.settings import AppSettings
from services.domain.contracts import RequestInput
from services.storage.database import database
from tests.test_domain import worksheet_data


@pytest.fixture(scope="module")
def http_setup(neon_store, tmp_path_factory):
    url, schema = neon_store
    folder = tmp_path_factory.mktemp("api-private")
    key, connection = folder / "csrf", folder / "database-url"
    key.write_text(secrets.token_urlsafe(48))
    key.chmod(0o600)
    connection.write_text(str(url))
    connection.chmod(0o600)
    password = secrets.token_urlsafe(24)
    with database(url, schema=schema) as conn:
        owner = provision_user(conn, "http_owner", "HTTP assertion owner", password)
        provision_user(conn, "http_other", "HTTP assertion other", password)
    settings = AppSettings(database_url_file=connection, csrf_key_file=key, database_schema=schema)
    app = create_app(settings)
    with TestClient(app, base_url="https://localhost:8443") as client:
        result = client.post(
            "/api/v1/auth/login",
            json={"username": "http_owner", "password": password},
            headers={"Origin": "https://localhost:8443"},
        )
        assert result.status_code == 200
        csrf = result.json()["data"]["csrf_token"]
        yield (
            app,
            client,
            {"Origin": "https://localhost:8443", "X-CSRF-Token": csrf},
            password,
            owner,
        )


def save(client, headers, body=None, **options):
    return client.post(
        "/api/v1/requests",
        json=body or worksheet_data(),
        headers={**headers, "Idempotency-Key": str(uuid4()), **options},
    )


def test_cookie_origin_csrf_and_unknown_fields(http_setup):
    app, client, headers, password, _ = http_setup
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "http_other", "password": password},
        headers={"Origin": "https://evil.invalid"},
    )
    assert response.status_code == 403
    response = save(client, {"Origin": headers["Origin"]})
    assert response.status_code == 403
    body = worksheet_data()
    body["approved"] = True
    response = save(client, headers, body)
    assert response.status_code == 422 and "approved" in response.json()["field_errors"]
    response = client.post(
        "/api/v1/requests",
        content=b"x" * (2 * 1024 * 1024 + 1),
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    with TestClient(app, base_url="https://localhost:8443") as other:
        response = other.post(
            "/api/v1/auth/login",
            json={"username": "http_other", "password": password},
            headers={"Origin": headers["Origin"]},
        )
        cookie = response.headers["set-cookie"]
        assert all(
            value in cookie for value in (COOKIE, "Secure", "HttpOnly", "SameSite=lax", "Path=/")
        )
        assert "Domain=" not in cookie


def test_persistence_history_conflict_and_idempotency(http_setup):
    _, client, headers, _, _ = http_setup
    assert client.get("/api/v1/requests").json()["data"]["requests"] == []
    body, key = worksheet_data(), str(uuid4())
    response = save(client, headers, body, **{"Idempotency-Key": key})
    assert response.status_code == 201
    saved = response.json()["data"]
    repeat = save(client, headers, body, **{"Idempotency-Key": key})
    assert repeat.json()["data"]["id"] == saved["id"]
    body["name"] = "Revised HTTP assertion"
    assert save(client, headers, body, **{"Idempotency-Key": key}).status_code == 409
    route = f"/api/v1/requests/{saved['id']}"
    edited = client.patch(
        route, json=body, headers={**headers, "If-Match": '"1"', "Idempotency-Key": str(uuid4())}
    )
    assert edited.status_code == 200 and edited.json()["data"]["version"] == 2
    conflict = client.patch(
        route, json=body, headers={**headers, "If-Match": '"1"', "Idempotency-Key": str(uuid4())}
    )
    assert conflict.status_code == 412 and conflict.json()["current_version"] == 2
    assert client.get(route).headers["etag"] == '"2"'
    assert client.get(route + "/history").json()["data"] == [2, 1]
    assert client.get(route + "?version=1").json()["data"]["worksheet"]["name"] != body["name"]
    assert client.get(route).json()["data"]["worksheet"]["budget"] == "100.00"


def test_owner_denial_profile_admission_and_worker_fail_closed(http_setup):
    app, client, headers, password, _ = http_setup
    response = save(client, headers)
    request_id = response.json()["data"]["id"]
    with TestClient(app, base_url="https://localhost:8443") as other:
        auth = other.post(
            "/api/v1/auth/login",
            json={"username": "http_other", "password": password},
            headers={"Origin": headers["Origin"]},
        )
        other_headers = {
            "Origin": headers["Origin"],
            "X-CSRF-Token": auth.json()["data"]["csrf_token"],
        }
        assert other.get(f"/api/v1/requests/{request_id}").status_code == 404
        assert other.get(f"/api/v1/requests/{request_id}/history").status_code == 404
        assert (
            other.post(
                f"/api/v1/requests/{request_id}/inspections",
                json={"current_version": 1, "public_scope_seen": True},
                headers={**other_headers, "If-Match": '"1"', "Idempotency-Key": str(uuid4())},
            ).status_code
            == 404
        )
        assert other.get("/api/v1/requests").json()["data"]["requests"] == []
    body = worksheet_data()
    body["sources"] = [
        {
            "label": "Policy assertion",
            "url": "https://vendor.example.com/offer",
            "profile_id": "not_admitted",
            "profile_version": 1,
        }
    ]
    assert save(client, headers, body).status_code == 422
    worker = client.post(
        f"/api/v1/requests/{request_id}/inspections",
        json={"current_version": 1, "public_scope_seen": True},
        headers={**headers, "If-Match": '"1"', "Idempotency-Key": str(uuid4())},
    )
    assert worker.status_code == 503 and worker.json()["code"] == "WORKER_UNAVAILABLE"
    assert client.get("/health/ready").json() == {"status": "degraded"}


def test_archive_and_reauth_rotation_logout(http_setup):
    app, client, headers, password, _ = http_setup
    request_id = save(client, headers).json()["data"]["id"]
    route = f"/api/v1/requests/{request_id}"
    archived = client.post(
        route + "/archive", json={"current_version": 1}, headers={**headers, "If-Match": '"1"'}
    )
    assert archived.status_code == 200 and archived.json()["data"]["status"] == "archived"
    assert (
        client.patch(
            route,
            json=worksheet_data(),
            headers={**headers, "If-Match": '"1"', "Idempotency-Key": str(uuid4())},
        ).status_code
        == 409
    )
    # Use an independent session so rotation does not alter the other test fixture.
    with TestClient(app, base_url="https://localhost:8443") as other:
        login = other.post(
            "/api/v1/auth/login",
            json={"username": "http_other", "password": password},
            headers={"Origin": headers["Origin"]},
        )
        old_token = other.cookies.get(COOKIE)
        other_headers = {
            "Origin": headers["Origin"],
            "X-CSRF-Token": login.json()["data"]["csrf_token"],
        }
        reauth = other.post(
            "/api/v1/auth/reauth", json={"password": password}, headers=other_headers
        )
        assert reauth.status_code == 200 and other.cookies.get(COOKIE) != old_token
        new_token = other.cookies.get(COOKIE)
        other.cookies.clear()
        other.cookies.set(COOKIE, old_token)
        assert other.get("/api/v1/auth/session").status_code == 401
        other.cookies.clear()
        other.cookies.set(COOKIE, new_token)
        other_headers["X-CSRF-Token"] = reauth.json()["data"]["csrf_token"]
        assert other.post("/api/v1/auth/logout", json={}, headers=other_headers).status_code == 204
        other.cookies.set(COOKIE, new_token)
        assert other.get("/api/v1/auth/session").status_code == 401


def test_concurrent_idempotency_is_one_durable_resource(neon_store, http_setup):
    from services.storage.requests import save as store_save

    url, schema = neon_store
    owner = http_setup[-1]
    worksheet = RequestInput.model_validate(worksheet_data())
    key = str(uuid4())

    def execute():
        with database(url, schema=schema) as conn:
            return store_save(conn, owner, worksheet, key).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: execute(), range(2)))
    assert results[0] == results[1]


def test_idle_expiry_is_server_enforced(neon_store, http_setup):
    url, schema = neon_store
    app, _, headers, password, _ = http_setup
    with TestClient(app, base_url="https://localhost:8443") as other:
        login = other.post(
            "/api/v1/auth/login",
            json={"username": "http_other", "password": password},
            headers={"Origin": headers["Origin"]},
        )
        assert login.status_code == 200
        from services.api.auth import token_hash

        with database(url, schema=schema) as conn:
            conn.execute(
                "UPDATE sessions SET last_seen_at=%s WHERE token_hash=%s",
                (now_ms() - IDLE_MS, token_hash(other.cookies.get(COOKIE))),
            )
        assert other.get("/api/v1/auth/session").status_code == 401


def test_job_event_replay_owner_cancellation_and_cursor(http_setup, neon_store):
    from services.storage import jobs

    app, _, _, password, owner = http_setup
    url, schema = neon_store
    with TestClient(app, base_url="https://localhost:8443") as client:
        auth = client.post(
            "/api/v1/auth/login",
            json={"username": "http_owner", "password": password},
            headers={"Origin": "https://localhost:8443"},
        )
        headers = {
            "Origin": "https://localhost:8443",
            "X-CSRF-Token": auth.json()["data"]["csrf_token"],
        }
        rid = save(client, headers).json()["data"]["id"]
        with database(url, schema=schema) as c:
            job = jobs.enqueue(c, owner, rid, 1, "sse_assertion")
        route = f"/api/v1/jobs/{job['id']}"
        assert client.get(route).json()["data"]["state"] == "queued"
        # Queued cancellation has no container and is immediately cleanup-complete.
        assert (
            client.post(route + "/cancel", json={}, headers=headers).json()["data"]["state"]
            == "cancelled"
        )
        response = client.get(route + "/events", headers={"Accept": "text/event-stream"})
        assert response.status_code == 200 and response.headers["x-accel-buffering"] == "no"
        events = [line[4:] for line in response.text.splitlines() if line.startswith("id: ")]
        assert len(events) == 2 and int(events[1]) > int(events[0])
        assert "lease" not in response.text and "fence" not in response.text
        resumed = client.get(
            route + "/events", headers={"Accept": "text/event-stream", "Last-Event-ID": events[0]}
        )
        assert f"id: {events[0]}\n" not in resumed.text and f"id: {events[1]}\n" in resumed.text
        assert (
            client.get(route + "/events", headers={"Last-Event-ID": "invalid"}).status_code == 422
        )
        with TestClient(app, base_url="https://localhost:8443") as other:
            other.post(
                "/api/v1/auth/login",
                json={"username": "http_other", "password": password},
                headers={"Origin": "https://localhost:8443"},
            )
            assert other.get(route).status_code == 404
            assert (
                other.get(route + "/events", headers={"Accept": "text/event-stream"}).status_code
                == 404
            )
