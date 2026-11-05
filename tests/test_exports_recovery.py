"""Offline renderer, byte manifests and authenticated backup format boundaries."""

import hashlib
import io
import json
import os
import zipfile

import pytest

from services.artifacts.exports import build, pdf
from services.artifacts.store import BinaryStore
from services.domain.contracts import content_hash
from services.domain.releases import ReceiptView
from services.storage.database import migrations
from services.storage.recovery import TABLES, decrypt, encrypt


def record():
    return {
        "id": "render assertion",
        "request_version": 1,
        "scope": "Internal assertion only",
        "committed_at": "2026-11-05T00:00:00Z",
        "worksheet": {
            "name": "Unicode assertion é <script>",
            "budget_cents": 100,
            "required_by": "2027-01-01T00:00:00Z",
            "timezone": "UTC",
            "items": [],
        },
        "approval_id": "assertion",
        "approval_hash": "a" * 64,
        "approved_packet": {"comparison": {"sources": []}},
        "fresh_sources": [],
    }


def test_pdf_is_offline_deterministic_and_packet_manifest_covers_exact_bytes():
    from uuid import uuid4

    value = record()
    a, b = pdf(value), pdf(value)
    assert a == b and a.startswith(b"%PDF-")
    receipt = ReceiptView(
        id=uuid4(),
        request_id=uuid4(),
        request_version=1,
        committed_at=value["committed_at"],
        record_hash=content_hash(value),
        record=value,
    )
    packet = build(receipt, "zip", [])
    assert packet == build(receipt, "zip", [])
    with zipfile.ZipFile(io.BytesIO(packet)) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["receipt_record_hash"] == receipt.record_hash
        for name, metadata in manifest["files"].items():
            data = z.read(name)
            assert (
                hashlib.sha256(data).hexdigest() == metadata["sha256"]
                and len(data) == metadata["bytes"]
            )
        assert json.loads(z.read("receipt.json")) == value


def test_binary_store_rejects_mutation_links_and_public_modes(tmp_path):
    directory = tmp_path / "exports"
    with BinaryStore(directory) as store:
        digest = store.put_bytes(b"bounded export assertion")
        assert store.read(digest) == b"bounded export assertion"
        file = directory / (digest + ".blob")
        file.write_bytes(b"modified")
        with pytest.raises(ValueError):
            store.read(digest)
        file.unlink()
        file.symlink_to(tmp_path / "other")
        with pytest.raises(ValueError):
            store.read(digest)


def test_backup_authentication_rejects_tampering_wrong_keys_and_changed_schema():
    secret = os.urandom(32)
    bundle = {
        "version": 1,
        "migrations": [[v, h] for v, _, h in migrations()],
        "tables": {t: [] for t in TABLES},
        "files": {},
    }
    encoded = json.dumps(bundle).encode()
    value = encrypt(encoded, secret)
    assert encoded not in value and decrypt(value, secret) == bundle
    assert encrypt(encoded, secret) != value
    for corrupt in (value[:-1], value[:-1] + bytes([value[-1] ^ 1]), b"wrong format"):
        with pytest.raises(ValueError):
            decrypt(corrupt, secret)
    with pytest.raises(ValueError):
        decrypt(value, os.urandom(32))
    bundle["migrations"][0][1] = "changed"
    with pytest.raises(ValueError):
        decrypt(encrypt(json.dumps(bundle).encode(), secret), secret)
