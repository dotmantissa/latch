"""Real anonymous demo isolation, bounded admission and absent approval authority."""

import secrets
from uuid import uuid4

from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.auth import DUMMY_HASH
from services.api.settings import AppSettings
from services.storage.database import database


def test_real_demo_isolation_origin_reauth_and_global_bound(neon_store, tmp_path):
    url, schema = neon_store
    dbfile, csrf = tmp_path / "database", tmp_path / "csrf"
    dbfile.write_text(str(url))
    dbfile.chmod(0o600)
    csrf.write_text(secrets.token_urlsafe(48))
    csrf.chmod(0o600)
    settings = AppSettings(
        database_url_file=dbfile, csrf_key_file=csrf, database_schema=schema, enable_demo=True
    )
    origin = settings.public_origin
    with TestClient(create_app(settings), base_url=origin) as client:
        assert (
            client.post(
                "/api/v1/auth/demo", json={}, headers={"Origin": "https://evil.invalid"}
            ).status_code
            == 403
        )
        response = client.post("/api/v1/auth/demo", json={}, headers={"Origin": origin})
        assert response.status_code == 200
        first = response.json()["data"]
        assert first["reauth_fresh"] is False
        h = {"Origin": origin, "X-CSRF-Token": first["csrf_token"]}
        assert (
            client.post(
                "/api/v1/auth/reauth", json={"password": secrets.token_urlsafe(24)}, headers=h
            ).status_code
            == 401
        )
        with TestClient(create_app(settings), base_url=origin) as other:
            second = other.post("/api/v1/auth/demo", json={}, headers={"Origin": origin}).json()[
                "data"
            ]
            assert second["user"]["id"] != first["user"]["id"]
            assert other.get("/api/v1/requests").json()["data"]["requests"] == []
        assert client.post("/api/v1/auth/logout", json={}, headers=h).status_code == 204
        assert client.get("/api/v1/auth/session").status_code == 401
    with database(url, schema=schema) as c:
        for _ in range(62):
            c.execute(
                "INSERT INTO users VALUES(%s,%s,'Bound assertion',%s,true,1,1)",
                (uuid4(), "demo_" + uuid4().hex, DUMMY_HASH),
            )
    with TestClient(create_app(settings), base_url=origin) as client:
        assert (
            client.post("/api/v1/auth/demo", json={}, headers={"Origin": origin}).status_code == 429
        )
    with TestClient(
        create_app(settings.model_copy(update={"enable_demo": False})), base_url=origin
    ) as client:
        assert (
            client.post("/api/v1/auth/demo", json={}, headers={"Origin": origin}).status_code == 404
        )
