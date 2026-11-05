"""Populated isolated Neon backup/restore and authorized export checks, not buyer acceptance."""

import hashlib
import os
import secrets
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from services.api.app import create_app
from services.api.auth import COOKIE, new_session
from services.api.errors import ApiError
from services.api.settings import AppSettings
from services.artifacts.store import ArtifactStore
from services.storage import decisions, releases
from services.storage.database import database, direct_url
from services.storage.recovery import decrypt, restore, snapshot
from tests.test_release_storage import fresh_assertion, seed


def test_populated_encrypted_restore_and_authorized_export(neon_store, tmp_path):
    url, schema = neon_store
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    connection, csrf = folder / "database-url", folder / "csrf-key"
    connection.write_text(str(url))
    connection.chmod(0o600)
    csrf.write_text(secrets.token_urlsafe(48))
    csrf.chmod(0o600)
    settings = AppSettings(
        database_url_file=connection,
        csrf_key_file=csrf,
        database_schema=schema,
        evidence_dir=tmp_path / "original" / "evidence",
    )
    with database(url, schema=schema) as c:
        owner, rid, session, approval, capture, _, _, approve_body, packet = seed(c)
        attempt, _ = fresh_assertion(c, owner, rid, session, approval, capture)
        releases.finalize(c, attempt.id)
        released = releases.view(c, owner, attempt.id)
        assert released.state == "released", released.reason
        receipt = releases.receipt(c, owner, released.receipt_id)
        with pytest.raises(ApiError) as error:
            decisions.approve(c, owner, rid, session, approve_body, "another_approval")
        assert error.value.code == "ALREADY_RELEASED"
        token = new_session(c, owner)
    with ArtifactStore(settings.evidence_dir) as files:
        files.put(packet.pages[0].raster)
    app = create_app(settings)
    with TestClient(app, base_url=settings.public_origin) as client:
        client.cookies.set(COOKIE, token, domain="localhost.local", path="/")
        for format in ("json", "pdf", "zip"):
            response = client.get(f"/api/v1/releases/{receipt.id}/exports/{format}")
            assert response.status_code == 200, (
                response.text[:200] if format == "json" else response.status_code
            )
            assert (
                response.headers["x-content-sha256"] == hashlib.sha256(response.content).hexdigest()
            )
            assert response.headers["content-disposition"].startswith("attachment;")
            again = client.get(f"/api/v1/releases/{receipt.id}/exports/{format}")
            assert response.content == again.content
        client.cookies.clear()
        assert client.get(f"/api/v1/releases/{receipt.id}/exports/json").status_code == 401
    secret = os.urandom(32)
    backup = snapshot(settings, secret)
    bundle = decrypt(backup, secret)
    assert len(bundle["tables"]["receipts"]) == 1
    restored = None
    try:
        restored, counts = restore(
            settings, backup, secret, evidence_dir=tmp_path / "restored" / "evidence"
        )
        assert counts["receipts"] == 1 and counts["receipt_exports"] == 3
        with database(url, schema=restored) as c:
            value = releases.receipt(c, owner, receipt.id)
            assert value.record_hash == receipt.record_hash and value.record == receipt.record
            assert decisions.state(c, owner, rid).approval.state == "invalidated"
            assert (
                c.execute("SELECT count(*) AS n FROM sessions WHERE revoked_at IS NULL").fetchone()[
                    "n"
                ]
                == 0
            )
            assert c.execute("SELECT count(*) AS n FROM request_versions").fetchone()["n"] == 1
        with ArtifactStore(tmp_path / "restored" / "evidence") as files:
            assert files.read(packet.pages[0].raster.sanitized_hash) == packet.pages[0].raster.data
    finally:
        if restored:
            with psycopg.connect(direct_url(url), connect_timeout=10) as c:
                c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(restored)))
            (Path("var/restore-schemas") / restored).unlink()
