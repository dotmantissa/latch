# P0 isolated worker spike

This is an operator-run feasibility tool for the private Vultr worker. It is not the
durable supervisor service specified for P4. Do not run it on a machine containing
unrelated work. No image has been built or containment verified on this development host.

## Required worker boundary

Install Docker with a working gVisor `runsc` runtime on the actual Vultr worker. Configure
a dedicated internal Docker network with no direct internet route. Attach only the source
containers and the external egress proxy to it. The proxy must apply the reviewed profile
to each destination, resolve and pin only public addresses, verify TLS hostnames, deny
metadata and private ranges, and enforce exact navigation and allowed asset policies.
The host firewall must also deny containers access to host services, the control subnet,
metadata, arbitrary DNS, UDP and direct internet connections.

The spike requires these operator-managed controls. It does not install a permissive
proxy or change firewall rules. Failure to reach an address is only an observation, not
proof that the external network policy caused the failure. Review actual proxy/firewall
denial evidence and Chromium sandbox behavior before passing P0. Browser request routing
is a second check and cannot substitute for this boundary.

## Pinned image

The Playwright 1.64.1 Noble base image is pinned to the actual registry index digest.
[The provenance record](../infra/browser/PROVENANCE.json) includes platform digests and
the upstream seccomp file hash. The browser package and its transitive dependencies have
their own [lock](../infra/browser/uv.lock) and
[hashed requirements](../infra/browser/requirements.lock). The worker Python is the
base image's Python 3.12, separate from the control service's pinned Python 3.13.

Build on the worker from the project root:

```bash
docker build --file infra/browser/Dockerfile --tag latch-browser:p0 .
```

The context allowlist includes only the browser program and locked requirements. It does
not send the project credentials, database, historical research or local runtime directory
to the builder. Publish to your private registry only when authorized, then configure
`LATCH_BROWSER_IMAGE` with the resulting immutable `registry/image@sha256:...` reference.
The runner refuses tags, arbitrary flags, root execution and alternate runtime choices.
No resulting image digest is fabricated in the provenance record.

Configure these on the worker with its service manager or private environment:

| Variable | Value |
| --- | --- |
| LATCH_BROWSER_IMAGE | The actual built image reference including digest |
| LATCH_EGRESS_NETWORK | The dedicated internal network name |
| LATCH_EGRESS_PROXY | The explicit credential free internal HTTP proxy URL and port |
| LATCH_SECCOMP_FILE | The pinned seccomp file path, defaulting to the checkout file |
| LATCH_SOURCE_TASK_FILE | The actual consented buyer task and reviewed source profiles |
| LATCH_DATA_DIR | Private local worker evidence directory |

No inference key, provisioning token, buyer identity, budget, session, host path or Docker
socket enters the container. The fixed payload contains only reviewed public page URLs,
selectors, asset origins, observation mode and the egress proxy address.

## Actual observations

```bash
bash scripts/latch.sh worker
bash scripts/latch.sh worker --timeout-probe
```

The probe first checks the installed gVisor runtime, internal network, pinned image label
and seccomp hash. It creates an exact labeled operation, then verifies effective Docker
configuration before execution: nonroot UID, read only root, capability removal, bounded
CPU, RAM, swap, PIDs, shared memory and temporary storage. The watchdog runs in the host
process. The image has no authority to choose Docker flags or extend that deadline.

The capture mode uses a fresh Chromium context with its sandbox requested, exact reviewed
pages and bounded content regions. It captures actual visible source text and a PNG,
including configured terms. It rejects unsupported redirects, multiple matching regions,
empty text and content beyond caps. `complete` means that the configured regions were
captured within limits; it does not assert that the supplier supplied every needed term.

After capture, fixed scoped probes remove browser interception and attempt metadata,
private and loopback navigation plus direct public TCP. Only response or failure outcomes
are retained. No metadata body or private response is printed. Successful access to a
forbidden destination fails the eventual containment gate, even if the UI capture works.
Separately inspect Chromium's actual sandbox and the external enforcement logs.

Timeout mode deliberately waits beyond its fixed two second host watchdog. Both modes
remove only their exact labeled container, then check that it is absent. Output and logs
have independent byte caps. Raw browser errors are not logged to public reports.

The command stores private evidence under `var/p0` with mode 0600. `capture.json` can be
used by [the actual Vultr screenshot probe](P0.md). `worker_capture.json` and
`worker_timeout.json` preserve observations. The aggregate result stays `pending_review`;
exit zero means the probe ran, not that isolation or source fit is accepted.

## Interrupted probe recovery

Before container creation, `worker_active.json` records its random opaque task ID and
mode. If the host process dies, recover that ID and run:

```bash
bash scripts/latch.sh cleanup-worker --task-id THE_RECORDED_TASK_ID
```

The command accepts only the exact opaque ID and verifies the container label before
removing it. It never kills a container selected by source text, a broad name match or an
unrelated process. The P4 supervisor will later need managed independent watchdogs and
restart sweeping; this finite P0 tool does not claim to replace those services.
