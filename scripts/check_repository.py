#!/usr/bin/env python3
"""Check deliverable files without traversing ignored runtimes or exposing secret matches."""

import os
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
names = (
    subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    .decode()
    .split("\0")
)
patterns = [
    re.compile(rb"npg_" + rb"[A-Za-z0-9]{10,}"),
    re.compile(rb"postgres(?:ql)?://" + rb"[^/\s:]+:[^@\s]+@"),
    re.compile(rb"gh[pousr]_" + rb"[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_" + rb"[A-Za-z0-9_]{30,}"),
    re.compile(rb"-----BEGIN " + rb"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"Authorization: Bearer " + rb"[A-Za-z0-9_-]{20,}"),
]
failures = []
configured_secrets = []
for secret_name in ("database-url", "csrf-key", "vultr-api-key", "vultr-inference-key"):
    secret_path = ROOT / "private" / secret_name
    if secret_path.exists() and not secret_path.is_symlink():
        fd = os.open(secret_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_size > 8192):
                raise SystemExit("Configured secret file must be private, owned and bounded")
            configured_secrets.append(os.read(fd, 8192).strip())
        finally:
            os.close(fd)
for name in sorted(set(names) - {""}):
    path = ROOT / name
    if path.name.lower() in {"tasks.md", "agent.md", "agents.md"}:
        failures.append((name, "private_instruction_file"))
        continue
    if path.is_symlink():
        failures.append((name, "symlink"))
        continue
    if not path.is_file():
        continue
    data = path.read_bytes()
    if any(secret and secret in data for secret in configured_secrets):
        failures.append((name, "configured_credential"))
        continue
    for pattern in patterns:
        if pattern.search(data):
            failures.append((name, "credential_pattern"))
            break
if failures:
    for name, reason in failures:
        print(f"{name}: {reason}")
    raise SystemExit(1)
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
if any(Path(name).name.lower() in {"tasks.md", "agent.md", "agents.md"} for name in tracked):
    raise SystemExit("Private checklist or instruction file is tracked")
print(
    f"Checked {len(set(names) - {''})} deliverable files; "
    "no credential patterns or private instruction files."
)
