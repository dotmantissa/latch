"""Explicit operator setup, TTY account management and offline contract generation."""

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

from services.api.auth import HASHER, normalize_username, now_ms, provision_user
from services.api.settings import AppSettings
from services.common.source_policy import SourceProfile
from services.storage.database import database, initialize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["migrate", "create-user", "reset-password", "admit-profile", "openapi"]
    )
    parser.add_argument("--username")
    parser.add_argument("--display-name")
    parser.add_argument("--profile-file", type=Path)
    args = parser.parse_args()
    settings = AppSettings.from_environment()
    try:
        if args.command == "migrate":
            initialize(settings.database_url(), schema=settings.database_schema)
            settings.csrf_key_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not settings.csrf_key_file.exists():
                fd = os.open(settings.csrf_key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as out:
                    out.write(secrets.token_urlsafe(48))
            print("Application schema ready. Private session key ready.")
        elif args.command == "openapi":
            from services.api.app import create_app

            target = Path("packages/contracts/openapi.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(create_app(settings).openapi(), indent=2) + "\n")
            print("Generated public API contracts.")
        elif args.command in ("create-user", "reset-password"):
            if not sys.stdin.isatty() or not args.username:
                raise ValueError("Account management requires a TTY and username")
            password = getpass.getpass("Password (12 to 256 characters): ")
            if password != getpass.getpass("Repeat password: ") or not 12 <= len(password) <= 256:
                raise ValueError("Password does not meet the requirements")
            with database(settings.database_url(), schema=settings.database_schema) as conn:
                if args.command == "create-user":
                    provision_user(
                        conn, args.username, args.display_name or args.username, password
                    )
                else:
                    row = conn.execute(
                        "SELECT id FROM users WHERE username=%s FOR UPDATE",
                        (normalize_username(args.username),),
                    ).fetchone()
                    if row is None:
                        raise ValueError("Account not found")
                    at = now_ms()
                    conn.execute(
                        "UPDATE users SET password_hash=%s,password_changed_at=%s WHERE id=%s",
                        (HASHER.hash(password), at, row["id"]),
                    )
                    conn.execute(
                        "UPDATE sessions SET revoked_at=%s WHERE user_id=%s", (at, row["id"])
                    )
            print("Account updated.")
        else:
            if not args.profile_file:
                raise ValueError("A reviewed profile file is required")
            profile = SourceProfile.model_validate_json(args.profile_file.read_text())
            if int(profile.expires_at.timestamp() * 1000) <= now_ms():
                raise ValueError("Profile already expired")
            with database(settings.database_url(), schema=settings.database_schema) as conn:
                conn.execute(
                    "INSERT INTO source_profiles VALUES(%s,%s,%s,true,%s)",
                    (
                        profile.id,
                        profile.version,
                        Jsonb(profile.model_dump(mode="json")),
                        int(profile.expires_at.timestamp() * 1000),
                    ),
                )
            print("Reviewed profile admitted. Live source compatibility remains a separate gate.")
    except Exception as error:
        print(f"Operator action failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
