#!/usr/bin/env python3
"""Pinned operator access to the privately inventoried Vultr control host."""

import argparse
import ipaddress
import json
import shlex
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdin-file", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    state = json.loads((root / "private/vultr-control-setup.json").read_text())
    ip = ipaddress.ip_address(state["instance_ip"])
    if not ip.is_global or state["ssh_user"] != "latchdeploy" or not args.command:
        raise SystemExit("Inventoried public control host and command required")
    pin = root / "private/latch-control-known-hosts"
    if not pin.is_file() or pin.is_symlink():
        raise SystemExit("Existing private control host pin required")
    return subprocess.run(
        [
            "ssh",
            "-i",
            str(root / "private/latch-control-ed25519"),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + str(pin),
            "-o",
            "ConnectTimeout=15",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
            "latchdeploy@" + str(ip),
            shlex.join(args.command),
        ],
        input=args.stdin_file.read_bytes() if args.stdin_file else None,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
