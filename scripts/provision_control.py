#!/usr/bin/env python3
"""Provision the authorized separate Vultr web/control host with crash-safe inventory."""

import base64
import json
import os
import subprocess
from pathlib import Path

import httpx

from services.common.config import read_secret

STATE = Path("private/vultr-control-setup.json")
LABEL = "latch-control"


def save(value):
    temporary = STATE.with_suffix(".pending")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE)


def main():
    os.umask(0o077)
    key = Path("private/latch-control-ed25519")
    if not key.exists():
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "latch-control-deploy",
                "-f",
                str(key),
            ],
            check=True,
        )
    public = key.with_suffix(".pub").read_text().strip()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"label": LABEL}
    with httpx.Client(
        base_url="https://api.vultr.com/v2",
        timeout=30,
        trust_env=False,
        headers={"Authorization": "Bearer " + read_secret(Path("private/vultr-api-key"))},
    ) as client:
        response = client.get("/instances")
        response.raise_for_status()
        instances = [i for i in response.json()["instances"] if i["label"] == LABEL]
        if len(instances) > 1:
            raise ValueError("DUPLICATE_CONTROL_HOST")
        if instances:
            instance = instances[0]
        else:
            keys = client.get("/ssh-keys")
            keys.raise_for_status()
            matches = [k for k in keys.json()["ssh_keys"] if k["name"] == LABEL]
            if len(matches) > 1:
                raise ValueError("DUPLICATE_CONTROL_KEY")
            if matches:
                ssh_key = matches[0]
                if ssh_key["ssh_key"].strip().split()[:2] != public.split()[:2]:
                    raise ValueError("CONTROL_KEY_MISMATCH")
            else:
                state["operation"] = "ssh_key_create_started"
                save(state)
                result = client.post("/ssh-keys", json={"name": LABEL, "ssh_key": public})
                result.raise_for_status()
                ssh_key = result.json()["ssh_key"]
            state["ssh_key_id"] = ssh_key["id"]
            state["operation"] = "instance_create_started"
            state["plan"] = "vc2-2c-4gb"
            state["monthly_cost_usd"] = 20
            save(state)
            cloud = "\n".join(
                [
                    "#cloud-config",
                    "hostname: latch-control",
                    "users:",
                    "  - name: latchdeploy",
                    "    groups: [sudo]",
                    "    shell: /bin/bash",
                    "    lock_passwd: true",
                    "    sudo: ['ALL=(ALL) NOPASSWD:ALL']",
                    "    ssh_authorized_keys:",
                    "      - " + public,
                    "ssh_pwauth: false",
                    "disable_root: true",
                    "package_update: true",
                    "packages: [ufw, ca-certificates, curl, cryptsetup, e2fsprogs]",
                    "runcmd:",
                    "  - ufw default deny incoming",
                    "  - ufw default allow outgoing",
                    "  - ufw allow 22/tcp",
                    "  - ufw allow 80/tcp",
                    "  - ufw allow 443/tcp",
                    "  - ufw --force enable",
                    "",
                ]
            )
            result = client.post(
                "/instances",
                json={
                    "label": LABEL,
                    "hostname": LABEL,
                    "region": "atl",
                    "plan": state["plan"],
                    "os_id": 2284,
                    "sshkey_id": [ssh_key["id"]],
                    "enable_ipv6": False,
                    "user_data": base64.b64encode(cloud.encode()).decode(),
                    "backups": "disabled",
                },
            )
            result.raise_for_status()
            instance = result.json()["instance"]
        state.update(
            instance_id=instance["id"],
            instance_ip=instance["main_ip"],
            ssh_user="latchdeploy",
            operation="instance_found",
            plan=instance["plan"],
            region=instance["region"],
        )
        save(state)
        print(
            json.dumps(
                {
                    "status": "control_host_provisioned",
                    "label": LABEL,
                    "plan": instance["plan"],
                    "monthly_cost_usd": 20,
                    "region": instance["region"],
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_class": type(error).__name__}))
        raise SystemExit(1) from None
