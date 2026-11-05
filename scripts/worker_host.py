#!/usr/bin/env python3
"""Operator SSH helper for the one privately recorded, pinned Latch worker."""

import argparse
import ipaddress
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdin-file", type=Path)
    parser.add_argument(
        "--tunnel",
        action="store_true",
        help="Forward only local127.0.0.1:9443 to the private mTLS supervisor",
    )
    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="Trusted operator remote command arguments"
    )
    args = parser.parse_args()
    if not args.command and not args.tunnel:
        parser.error("A trusted operator command is required")
    if args.tunnel and (args.command or args.stdin_file):
        parser.error("Tunnel mode accepts no remote command or input file")
    os.chdir(ROOT)
    state = json.loads((ROOT / "private/vultr-worker-setup.json").read_text())
    address = ipaddress.ip_address(state["instance_ip"])
    if not address.is_global or state.get("ssh_user") != "linuxuser":
        raise SystemExit("Verified public worker address and limited SSH user required")
    key = ROOT / "private/latch-worker-ed25519"
    known_hosts = ROOT / "private/latch-worker-known-hosts"
    if not known_hosts.is_file() or known_hosts.is_symlink() or key.is_symlink():
        raise SystemExit("Private SSH key and existing worker host pin required")
    import shlex

    body = args.stdin_file.read_bytes() if args.stdin_file else None
    command = [
        "ssh",
        "-i",
        str(key),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(known_hosts),
    ]
    if args.tunnel:
        command += [
            "-o",
            "ExitOnForwardFailure=yes",
            "-N",
            "-L",
            "127.0.0.1:9443:127.0.0.1:9443",
            "linuxuser@" + str(address),
        ]
    else:
        command += ["linuxuser@" + str(address), shlex.join(args.command)]
    return subprocess.run(
        command,
        input=body,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
