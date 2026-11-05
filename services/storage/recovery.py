"""Encrypted consistent logical snapshots and restore into a new isolated schema."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import sql
from psycopg.types.json import Jsonb

from services.api.settings import AppSettings
from services.artifacts.store import ArtifactStore, BinaryStore
from services.common.config import read_secret
from services.domain.contracts import canonical_json
from services.storage import jobs
from services.storage.database import database, initialize, migrations, verify_history

MAGIC = b"LATCH-BACKUP-1\n"
TABLES = (
    "schema_migrations",
    "users",
    "sessions",
    "source_profiles",
    "requests",
    "request_versions",
    "required_items",
    "supplier_sources",
    "idempotency",
    "jobs",
    "runner_slot",
    "job_attempts",
    "job_tasks",
    "source_captures",
    "captured_pages",
    "source_extractions",
    "review_heads",
    "field_reviews",
    "source_correspondence",
    "comparisons",
    "selections",
    "approvals",
    "approval_revocations",
    "release_attempts",
    "release_outcomes",
    "receipts",
    "receipt_exports",
    "events",
)


INTRODUCED = {
    "source_correspondence": 5,
    "comparisons": 6,
    "selections": 6,
    "approvals": 6,
    "approval_revocations": 6,
    "release_attempts": 7,
    "release_outcomes": 7,
    "receipts": 7,
    "receipt_exports": 8,
}


def version_tables(version):
    if not 4 <= version <= len(migrations()):
        raise ValueError("BACKUP_SCHEMA_UNSUPPORTED")
    return tuple(t for t in TABLES if INTRODUCED.get(t, 4) <= version)


def key(path):
    value = read_secret(path)
    if len(value) != 64:
        raise ValueError("BACKUP_KEY_REQUIRED")
    try:
        return bytes.fromhex(value)
    except ValueError:
        raise ValueError("BACKUP_KEY_REQUIRED") from None


def create_key(path):
    # The parent must already be the owned private directory, not an arbitrary destination.
    if path.parent != Path("private") or path.is_symlink():
        raise ValueError("PRIVATE_BACKUP_KEY_REQUIRED")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(os.urandom(32).hex())
        out.flush()
        os.fsync(out.fileno())


def encrypt(body, secret):
    if len(body) > 64 * 1024 * 1024:
        raise ValueError("BACKUP_SIZE_LIMIT")
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(secret).encrypt(nonce, body, MAGIC)


def decrypt(value, secret):
    if not value.startswith(MAGIC) or len(value) > BinaryStore.limit:
        raise ValueError("BACKUP_FORMAT_INVALID")
    start = len(MAGIC)
    try:
        body = AESGCM(secret).decrypt(value[start : start + 12], value[start + 12 :], MAGIC)
        result = json.loads(body)
    except Exception:
        raise ValueError("BACKUP_AUTHENTICATION_FAILED") from None
    history = result.get("migrations", [])
    expected = [[v, h] for v, _, h in migrations()]
    if (
        result.get("version") != 1
        or history != expected[: len(history)]
        or set(result.get("tables", {})) != set(version_tables(len(history)))
    ):
        raise ValueError("BACKUP_SCHEMA_UNSUPPORTED")
    for blob in result["files"].values():
        data = base64.b64decode(blob["data"], validate=True)
        if hashlib.sha256(data).hexdigest() != blob["hash"] or len(data) != blob["bytes"]:
            raise ValueError("BACKUP_FILE_HASH_MISMATCH")
    return result


def snapshot(settings, secret):
    with database(
        settings.database_url(), schema=settings.database_schema, check_schema=False
    ) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        history = c.execute(
            "SELECT version,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        verify_history(history, complete=False)
        included = version_tables(len(history))
        tables, used = {}, 0
        for table in included:
            # JSONB keeps PostgreSQL scalar/time representations without Python repr leakage.
            rows = []
            with c.cursor(name="backup_" + table) as cursor:
                cursor.itersize = 16
                cursor.execute(
                    sql.SQL("SELECT to_jsonb(t) AS value FROM {} t").format(
                        sql.Identifier(table),
                    )
                )
                for row in cursor:
                    used += len(canonical_json(row["value"]).encode())
                    if used > 64 * 1024 * 1024 or len(rows) >= 10000:
                        raise ValueError("BACKUP_SIZE_LIMIT")
                    rows.append(row["value"])
            tables[table] = sorted(rows, key=canonical_json)
        files = {}
        with ArtifactStore(settings.evidence_dir) as images:
            for page in tables["captured_pages"]:
                digest = page["sanitized_png_hash"]
                if "evidence/" + digest in files:
                    continue
                data = images.read(digest, size=page["sanitized_bytes"])
                used += (len(data) * 4 + 2) // 3
                if used > 64 * 1024 * 1024:
                    raise ValueError("BACKUP_SIZE_LIMIT")
                files["evidence/" + digest] = {
                    "hash": digest,
                    "bytes": len(data),
                    "data": base64.b64encode(data).decode(),
                }
        with BinaryStore(settings.evidence_dir.parent / "exports") as exported:
            for output in tables.get("receipt_exports", []):
                digest = output["content_hash"]
                if "exports/" + digest in files:
                    continue
                data = exported.read(digest, size=output["bytes"])
                used += (len(data) * 4 + 2) // 3
                if used > 64 * 1024 * 1024:
                    raise ValueError("BACKUP_SIZE_LIMIT")
                files["exports/" + digest] = {
                    "hash": digest,
                    "bytes": len(data),
                    "data": base64.b64encode(data).decode(),
                }
        result = {
            "version": 1,
            "snapshot_at": jobs.clock(c),
            "migrations": [[r["version"], r["checksum"]] for r in history],
            "tables": tables,
            "files": files,
        }
    return encrypt(canonical_json(result).encode(), secret)


def restore(settings, value, secret, *, evidence_dir):
    bundle = decrypt(value, secret)  # Authenticate before any schema/file mutation.
    schema = "latch_test_" + uuid4().hex
    recovery = Path("var/restore-schemas")
    recovery.mkdir(mode=0o700, parents=True, exist_ok=True)
    (recovery / schema).write_text(schema)
    initialize(settings.database_url(), schema=schema)
    with (
        ArtifactStore(evidence_dir) as images,
        BinaryStore(evidence_dir.parent / "exports") as blobs,
    ):
        from types import SimpleNamespace

        for name, blob in bundle["files"].items():
            data = base64.b64decode(blob["data"], validate=True)
            if name == "evidence/" + blob["hash"]:
                images.put(SimpleNamespace(data=data, sanitized_hash=blob["hash"]))
            elif name == "exports/" + blob["hash"]:
                blobs.put_bytes(data)
            else:
                raise ValueError("BACKUP_FILE_SCOPE_INVALID")
    with database(settings.database_url(), schema=schema) as c:
        columns = c.execute(
            "SELECT table_name,column_name,data_type FROM information_schema.columns "
            "WHERE table_schema=%s ORDER BY ordinal_position",
            (schema,),
        ).fetchall()
        c.execute("ALTER TABLE receipts DISABLE TRIGGER receipt_release_guard")
        c.execute("ALTER TABLE receipts DISABLE TRIGGER receipt_eligibility_guard")
        included = version_tables(len(bundle["migrations"]))
        for table in included:
            if table in ("schema_migrations", "runner_slot"):
                continue
            meta = [col for col in columns if col["table_name"] == table]
            if table == "approvals" and len(bundle["migrations"]) < 9:
                meta = [col for col in meta if col["column_name"] != "generation"]
            names = [col["column_name"] for col in meta]
            values = bundle["tables"][table]
            if table == "approvals" and len(bundle["migrations"]) < 9:
                values = sorted(values, key=lambda r: (r["created_at"], r["id"]))
            for row in values:
                if set(row) != set(names):
                    raise ValueError("BACKUP_ROW_SCHEMA_INVALID")
                vals = [
                    Jsonb(row[col["column_name"]])
                    if col["data_type"] == "jsonb"
                    else row[col["column_name"]]
                    for col in meta
                ]
                c.execute(
                    sql.SQL("INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE VALUES ({})").format(
                        sql.Identifier(table),
                        sql.SQL(",").join(map(sql.Identifier, names)),
                        sql.SQL(",").join(sql.Placeholder() for _ in names),
                    ),
                    vals,
                )
        c.execute("ALTER TABLE receipts ENABLE TRIGGER receipt_release_guard")
        c.execute("ALTER TABLE receipts ENABLE TRIGGER receipt_eligibility_guard")
        # All prior login cookies are revoked after recovery. Worker task fences stay recorded
        # for explicit runner reconciliation; restoration never claims remote cleanup.
        c.execute("UPDATE sessions SET revoked_at=COALESCE(revoked_at,%s)", (jobs.clock(c),))
        for table, col in (("requests", "seq"), ("events", "id"), ("approvals", "generation")):
            c.execute(
                sql.SQL(
                    "SELECT setval(pg_get_serial_sequence(%s,%s),"
                    "COALESCE((SELECT max({})+1 FROM {}),1),false)"
                ).format(
                    sql.Identifier(col),
                    sql.Identifier(table),
                ),
                (schema + "." + table, col),
            )
        counts = {
            table: c.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(
                    sql.Identifier(table),
                )
            ).fetchone()["n"]
            for table in included
        }
        if any(counts[t] != len(bundle["tables"][t]) for t in included if t != "schema_migrations"):
            raise ValueError("BACKUP_RESTORE_COUNT_MISMATCH")
        for row in c.execute("SELECT record_json,record_hash FROM receipts").fetchall():
            from services.domain.contracts import content_hash

            if content_hash(row["record_json"]) != row["record_hash"]:
                raise ValueError("BACKUP_RECEIPT_HASH_MISMATCH")
    return schema, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create-key", "backup", "restore"))
    parser.add_argument("--key-file", type=Path, default=Path("private/backup-key"))
    parser.add_argument("--backup-hash")
    parser.add_argument("--store", type=Path, default=Path("var/backups"))
    parser.add_argument("--restore-dir", type=Path, default=Path("var/restored/evidence"))
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "create-key":
            create_key(args.key_file)
            print("Private backup key created. Keep a separate secure recovery copy.")
            return
        settings, secret = AppSettings.from_environment(), key(args.key_file)
        with BinaryStore(args.store) as store:
            if args.command == "backup":
                digest = store.put_bytes(snapshot(settings, secret))
                print(json.dumps({"encrypted_backup_hash": digest}))
            else:
                value = store.read(args.backup_hash)
                schema, counts = restore(settings, value, secret, evidence_dir=args.restore_dir)
                print(
                    json.dumps(
                        {
                            "isolated_restored_schema": schema,
                            "counts": counts,
                            "production_cutover": "not_performed",
                            "sessions": "revoked",
                        }
                    )
                )
    except Exception:
        print("Recovery operation failed. Check the exact isolated schema recovery note.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
