#!/usr/bin/env python3
"""Check deliverable files without traversing ignored runtimes or exposing secret matches."""

import re
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
    re.compile(rb"gh[pousr]_" + rb"[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_" + rb"[A-Za-z0-9_]{30,}"),
    re.compile(rb"-----BEGIN " + rb"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"Authorization: Bearer " + rb"[A-Za-z0-9_-]{20,}"),
]
failures = []
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
