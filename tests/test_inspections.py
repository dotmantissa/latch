"""Real database admission boundaries; no supplier or buyer acceptance asserted."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from services.api.app import create_app
from services.api.auth import provision_user
from services.api.settings import AppSettings
from services.common.source_policy import SourceProfile, profile_hash
from services.domain.inspections import ProposedPlan
from services.storage import inspections, jobs
from services.storage.database import database
from tests.test_domain import worksheet_data


def test_actual_inspection_admission_replay_freshness_queue_and_plan(neon_store, tmp_path):
    url, schema = neon_store
    connection, csrf = tmp_path / "db", tmp_path / "csrf"
    connection.write_text(str(url))
    connection.chmod(0o600)
    csrf.write_text(secrets.token_urlsafe(48))
    csrf.chmod(0o600)
    settings = AppSettings(
        database_url_file=connection,
        csrf_key_file=csrf,
        database_schema=schema,
        enable_inspections=True,
    )
    profile = SourceProfile(
        id="admission_assertion",
        version=1,
        origin="https://vendor.example.com",
        offer_paths=["/offer"],
        main_selector="main",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    password, holder = secrets.token_urlsafe(24), uuid4()

    def db():
        return database(url, schema=schema)

    with db() as c:
        owner = provision_user(c, "admission_owner", "Admission assertion", password)
        provision_user(c, "admission_other", "Other assertion", password)
        c.execute(
            "INSERT INTO source_profiles VALUES(%s,1,%s,true,%s)",
            (
                profile.id,
                Jsonb(profile.model_dump(mode="json")),
                int(profile.expires_at.timestamp() * 1000),
            ),
        )
    with TestClient(create_app(settings), base_url="https://localhost:8443") as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admission_owner", "password": password},
            headers={"Origin": settings.public_origin},
        )
        h = {"Origin": settings.public_origin, "X-CSRF-Token": login.json()["data"]["csrf_token"]}
        body = worksheet_data()
        body["sources"] = [
            {
                "label": "Admission assertion",
                "url": profile.origin + "/offer",
                "profile_id": profile.id,
                "profile_version": 1,
            }
        ]

        def save():
            r = client.post(
                "/api/v1/requests", json=body, headers={**h, "Idempotency-Key": str(uuid4())}
            )
            assert r.status_code == 201
            return r.json()["data"]["id"]

        rid = save()
        route = f"/api/v1/requests/{rid}"

        def begin(ack=True, key=None, version=1):
            return client.post(
                route + "/inspections",
                json={"current_version": version, "public_scope_seen": ack},
                headers={**h, "If-Match": f'"{version}"', "Idempotency-Key": key or str(uuid4())},
            )

        assert client.get(route + "/inspection").json()["data"]["reason"] == "WORKER_UNAVAILABLE"
        assert begin().status_code == 503
        assert begin(False).status_code == 422
        profiles = [{"id": profile.id, "version": 1, "hash": profile_hash(profile)}]
        with db() as c:
            inspections.heartbeat(c, holder, True, profiles)
        assert client.get("/health/ready").json()["status"] == "ready"
        assert client.get(route + "/inspection").json()["data"]["enabled"]
        assert begin(version=2).status_code == 412
        key = str(uuid4())
        admitted = begin(key=key)
        assert admitted.status_code == 202
        job_id = admitted.json()["data"]["id"]
        with db() as c:
            inspections.heartbeat(c, holder, False, [])
        assert begin(key=key).json()["data"]["id"] == job_id
        assert begin(key=key, version=2).status_code == 409
        with db() as c:
            inspections.heartbeat(c, holder, True, profiles)
            c.execute("UPDATE runner_health SET checked_at=checked_at-75001")
        assert client.get("/health/ready").json()["status"] == "degraded"
        with db() as c:
            inspections.heartbeat(c, holder, True, [{**profiles[0], "hash": "a" * 64}])
        assert (
            client.get(route + "/inspection").json()["data"]["reason"]
            == "SOURCE_PROFILE_UNAVAILABLE"
        )
        with db() as c:
            inspections.heartbeat(c, holder, True, profiles)
        assert begin().status_code == 409
        rid2 = save()
        rid3 = save()

        def start(r):
            return client.post(
                f"/api/v1/requests/{r}/inspections",
                json={"current_version": 1, "public_scope_seen": True},
                headers={**h, "If-Match": '"1"', "Idempotency-Key": str(uuid4())},
            )

        assert start(rid2).status_code == 202
        assert start(rid3).status_code == 429
        with TestClient(create_app(settings), base_url=settings.public_origin) as other:
            login = other.post(
                "/api/v1/auth/login",
                json={"username": "admission_other", "password": password},
                headers={"Origin": settings.public_origin},
            )
            oh = {
                "Origin": settings.public_origin,
                "X-CSRF-Token": login.json()["data"]["csrf_token"],
            }
            assert other.get(route + "/inspection").status_code == 404
            assert (
                other.post(
                    route + "/inspections",
                    json={"current_version": 1, "public_scope_seen": True},
                    headers={**oh, "If-Match": '"1"', "Idempotency-Key": str(uuid4())},
                ).status_code
                == 404
            )
        with db() as c:
            job = jobs.claim(c, holder)
            sid = c.execute(
                "SELECT id FROM supplier_sources WHERE request_id=%s", (job["request_id"],)
            ).fetchone()["id"]
            plan = ProposedPlan(source_order=[sid], workflow="capture_extract_verify")
            inspections.save_plan(c, job, holder, plan, {"total_tokens": 1})
            jobs.cancel(c, owner, job["id"])
            jobs.finish(c, job["id"], job["fence"], holder, success=False)
        with db() as c:
            assert c.execute("SELECT count(*) AS n FROM inspection_plans").fetchone()["n"] == 1
        with pytest.raises(psycopg.errors.RaiseException):
            with db() as c:
                c.execute("UPDATE inspection_plans SET plan_hash=%s", ("b" * 64,))
        assert client.post(f"/api/v1/jobs/{job_id}/cancel", json={}, headers=h).status_code == 200
        assert client.get(route + "/inspection").json()["data"]["job"]["state"] == "cancelled"
