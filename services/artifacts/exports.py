"""Deterministic authorized exports, no supplier fetch or template execution."""

import hashlib
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from services.api.errors import ApiError
from services.artifacts.store import BinaryStore
from services.domain.contracts import canonical_json

VERSION = "receipt-export-v1"
MEDIA = {"json": "application/json", "pdf": "application/pdf", "zip": "application/zip"}


def pdf(record):
    body = canonical_json(record).encode()
    if len(body) > 2 * 1024 * 1024:
        raise ApiError(503, "EXPORT_RENDER_LIMIT")
    with tempfile.TemporaryFile() as out:
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("render.py").absolute())],
                input=body,
                stdout=out,
                stderr=subprocess.DEVNULL,
                timeout=12,
                env={"LANG": "C.UTF-8"},
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            raise ApiError(503, "EXPORT_RENDER_TIMEOUT") from None
        if result.returncode or out.tell() > 2 * 1024 * 1024:
            raise ApiError(503, "EXPORT_RENDER_FAILED")
        out.seek(0)
        value = out.read(2 * 1024 * 1024 + 1)
    if not value.startswith(b"%PDF-"):
        raise ApiError(503, "EXPORT_RENDER_FAILED")
    return value


def build(receipt, format, images):
    if format not in MEDIA:
        raise ApiError(404, "NOT_FOUND", "error.notFound")
    body = (canonical_json(receipt.record) + "\n").encode()
    if format == "json":
        return body
    rendered = pdf(receipt.record)
    if format == "pdf":
        return rendered
    files = {"receipt.json": body, "receipt.pdf": rendered}
    source_index = []
    for page, image in images:
        name = "sources/" + str(page["id"]) + ".png"
        files[name] = image
        text_name = "sources/" + str(page["id"]) + ".txt"
        files[text_name] = page["source_text"].encode()
        source_index.append(
            {
                "artifact_id": str(page["id"]),
                "capture_id": str(page["capture_id"]),
                "url": page["source_url"],
                "raster_file": name,
                "text_file": text_name,
                "raster_hash": page["sanitized_png_hash"],
                "text_hash": page["text_hash"],
            }
        )
    files["source-index.json"] = (canonical_json(source_index) + "\n").encode()
    files["README.txt"] = (
        "Latch internal decision packet\n\n" + receipt.record["scope"] + "\n"
        "This packet contains private requester and supplier evidence. Sharing is manual.\n"
        "Source claims and requester review are not supplier guarantees.\n"
        "receipt.json is the authoritative immutable record; the PDF is an alternate view.\n"
        "manifest.json records ordinary SHA256 hashes of the included bytes.\n"
        "The receipt record uses Latch canonical schema hashing, shown by the application.\n"
    ).encode()
    files["manifest.json"] = (
        canonical_json(
            {
                "version": VERSION,
                "receipt_record_hash": receipt.record_hash,
                "files": {
                    name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                    for name, data in sorted(files.items())
                },
            }
        )
        + "\n"
    ).encode()
    if sum(map(len, files.values())) > BinaryStore.limit:
        raise ApiError(503, "EXPORT_SIZE_LIMIT")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            archive.writestr(info, value)
    value = output.getvalue()
    if len(value) > BinaryStore.limit:
        raise ApiError(503, "EXPORT_SIZE_LIMIT")
    return value
