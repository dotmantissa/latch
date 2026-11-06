# Vultr deployment

The public app is https://latch.64.177.55.57.sslip.io. Its temporary hostname resolves to the Vultr control VM and has a publicly trusted HTTPS certificate. Both application hosting and sandbox orchestration run on Vultr, as required by the official Blast Radius Zero challenge.

| Component | Location and responsibility |
| --- | --- |
| Caddy | Control VM, ports 80/443, automatic HTTPS, proxy to loopback API |
| FastAPI + built React assets | Control VM, latch-api user, 127.0.0.1:8080 |
| Durable runner | Control VM, latch-runner user, model planning and evidence publication |
| Vultr Serverless Inference | qwen3.8-flash-next; planning, text extraction and raster correspondence |
| Neon | TLS connection; durable jobs, versions, plans, evidence indexes and authority records |
| Private supervisor | Separate worker VM, loopback 9443, fixed commands and mutual TLS |
| gVisor / Playwright | Worker VM, disposable nonroot Chromium tasks, restricted proxy/network |
| Persistent artifacts | Control VM, encrypted 4 GiB LUKS2 filesystem, nodev/nosuid/noexec |

The control plan is vc2-2c-4gb: 2 vCPU, 4 GiB RAM, 80 GiB disk, provider listed price USD 20/month. Worker and inference are separate resources with their own charges. The operator can replace the temporary hostname with a domain by updating Caddy and LATCH_PUBLIC_ORIGIN together.

## Reproduce the release

Build locally with the pinned Python 3.13.18, uv 0.13.7 and Node 24.22.2 toolchain. The Python control dependencies are pinned with hashes in infra/control/requirements.lock. The frontend uses package-lock.json and emits dist/.

```bash
bash scripts/bootstrap.sh
PATH="$PWD/.tools/node/node_modules/node/bin:$PATH" .tools/node/node_modules/node/bin/node .tools/node/node_modules/npm/bin/npm-cli.js run build
.venv/bin/python -m services.api.operator migrate
```

Provision/recover the exact labelled control instance with scripts/provision_control.py. It inventories the provider first and does not automatically retry creation POSTs. Keep private/vultr-control-setup.json and the dedicated operator key and host pin in private recovery storage. The scripts/control_host.py helper uses that exact inventoried host and existing pin.

Stage public services/assets/dist, the hashed requirements, setup_control.sh and the pinned uv binary in /opt/latch-control. Stage owned private input files in the root-only /etc/latch/bootstrap directory. The installer expects database-url, csrf-key, backup-key, vultr-inference-key, volume-key, tunnel-key, worker-known-hosts, tls/{ca.crt,runner.crt,runner.key} and control.json containing hostname, worker_ip and model. Never put those files in the repository or a public release archive. Initial host pinning uses operator SSH keyscan trust on first use; subsequent transfers require the stored pin.

Run scripts/setup_control.sh as root on latch-control. It installs the encrypted filesystem and separate services, preserving an existing volume. Initial creation is explicitly bounded to a new absent image; do not reformat an existing volume. Activate API/runner only after the schema and exact source profile are verified. Applied migrations 001–011 are immutable.

The worker tunnel uses a dedicated account/key with source IP restriction, local forwarding only to 127.0.0.1:9443, no PTY, agent forwarding or shell command. The Vultr worker firewall admits the exact control IP on SSH in addition to the operator IP. The worker operator key is never copied to the control host. Browser firewall rules and public egress admission remain unchanged.

## Credentials and artifacts

Model and tunnel keys belong only to latch-runner. Session and backup keys belong only to latch-api. Each service has its own owned mode 0600 database file; neither credential enters worker tasks. The encrypted volume key is root-only, with an ignored private operator recovery copy. Database connection TLS and required channel binding are retained. Explicit system CA/client certificate paths prevent libpq from trying a service home directory hidden by ProtectHome.

Artifact directories are owned by a configured service UID, group latch-artifacts, mode 2770. Files are 0640. Readers accept only configured service owners and the expected GID, reject other access, group-writable files, symlinks, hardlinks and hash changes. Default local stores remain 0700/0600. Service hardening includes NoNewPrivileges, ProtectSystem, ProtectHome, private temporary files/devices, bounded memory/tasks and no capabilities. A shared writable artifact directory is an explicit trusted API/runner boundary, not protection against root or a compromised peer service.

Quarantine is runner-private on the encrypted volume. Captured public source text and sanitized screenshots are retained with saved versions. Archive does not delete records. The demo disclosure covers capture and inference; automatic retention expiry is not implemented. Keep real buyer data out of anonymous demonstrations.

## Operations and recovery

```bash
systemctl is-active caddy latch-api latch-runner latch-tunnel latch-storage
systemctl start latch-backup.service
journalctl -u latch-backup.service --no-pager
```

The daily backup timer stores bounded encrypted consistent snapshots as content-addressed blobs on the encrypted volume. Keep its hash and copy the encrypted blob off-host using pinned operator SSH. Key recovery material must be kept separately from public files and backup envelopes. A local ignored recovery copy is retained for this release; an independent offline operator key copy and provider disaster recovery remain operational work.

Restore uses a newly generated isolated schema and private artifact directory, checks counts/hashes and revokes sessions. Never cut production over merely because an isolated restore passed. To recover an interrupted job, restart the tunnel and runner; expired fences are revoked before recapture and publication is cleanup-confirmed. Readiness is degraded when worker/model health is stale or unavailable.

The demo is deliberately finite: 64 anonymous accounts total, two inspections per account, per-IP admission throttles, global queue 16 and per-owner active queue 2. One API process owns the process-local limiter; run one process until a shared limiter exists. A source is enabled only when its active unexpired profile hash matches the worker's fresh authenticated health report. Replacing an expired profile requires a new version and matching worker policy; do not silently widen egress.
