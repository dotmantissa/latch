# Durable worker and runner

The private supervisor and Postgres runner implement the job infrastructure for P4.
They have actual technical documentation capture and interruption checks, separate from
supplier and buyer acceptance. The public inspection endpoint stays gated. A technical
profile is installed only on the worker; no supplier profile, buyer account or request is
seeded in the application database.

## Private service boundary

The supervisor listens on 127.0.0.1:9443 on the existing worker and requires TLS 1.3,
its private channel CA and a client certificate with the runner URI identity. The browser
has none of these credentials. The worker firewall admits no public supervisor port.
The operator's pinned SSH tunnel forwards only this endpoint. SSH remains key-only,
root login stays disabled, remote forwarding is disabled and PermitOpen restricts local
forwarding to 127.0.0.1:9443.

The separate latch-supervisor Linux service has access to Docker and owns its private
state directory; Docker access is host administration authority. It receives no Neon,
buyer-session or Vultr key. Systemd restricts its filesystem, process resources and
capabilities. The parent data directory permits traversal while child files/directories
retain their private owner/group modes. The egress service and browser boundary retain
the earlier verified networking controls.

A task command contains only task/job/fence UUIDs, reviewed profile identity/version and
one admitted public URL. The operator config selects the image, proxy, limits, selectors,
terms page and asset origins. Callers cannot choose a mode, image, path, mount, flag,
selector, timeout or credential. HTTP handlers cap bodies and connection concurrency;
TLS handshakes happen in bounded threads with timeouts.

## Persistence and cleanup

Application jobs, attempts, task identities and status events persist in Neon. Migration
002 adds these records; migration 001 retains its original bytes. The migration runner
accepts only contiguous, checksum-verified history, serializes application upgrades and
refuses downgrades, altered history or an unsupported runtime schema. The current
application schema was empty immediately before applying 002. A populated isolated
version-1 upgrade preserved its account record. That check does not replace an encrypted
backup/restore or an operator recovery point for future populated application migrations.

One Postgres runner slot serializes claims across runner processes. Each attempt has a
new fence and holder, a 30 second lease, heartbeats within eight seconds and a fixed
180 second job deadline. An expired lease cannot be revived. No network call happens in
a database transaction. Source tasks are persisted before supervisor submission, so a
lost response can recover the same task identity. An old attempt cannot mark a new
attempt's artifacts or job complete.

The worker has an atomic, fsynced private lifecycle journal. This is host metadata and
quarantine, separate from the Neon application records. Task acceptance persists before
container creation. One active task is admitted globally. Containers use the same pinned
gVisor/Chromium policy, a fixed 90 second deadline, read-only filesystem, non-root user,
CPU/RAM/PID/tmpfs limits and external reviewed egress. Standard output and logs are bounded.

Cancellation remains pending while container creation or execution can still complete.
The executor records terminal cancellation only after exact labeled removal. A separately
managed sweep timer kills overdue/orphan containers even if the HTTP service is stopped;
service startup also reconciles interrupted journal records. Cleanup checks both the exact
opaque name and supervisor label, and never removes an unrelated container.

Before runner recovery, the worker durably revokes the old job fence. This also rejects a
late task submission that arrives after an absent task was recorded as cleaned. Cleanup
must be confirmed before requeue, and there is at most one recovery attempt. Every retry
captures fresh content. A missing worker leaves recovery pending instead of assuming
cleanup or producing a success.

## Quarantine and progress

Browser output is untrusted. The supervisor checks byte caps, complete page sets, exact
navigation chains, capture intervals, status, text/raster dimensions and hashes before
accepting a capture into private quarantine. Artifacts are available only through the
fenced mTLS channel after cleanup, with verified byte hashes and bounded streaming.
They are not exposed as public files or purchasing authority. Supplier completeness,
extraction, evidence review and release validation are later gates.

Job status and cancellation endpoints enforce the authenticated owner. Stored events use
server-authored phase fields; they contain no source text, model answer, prompt, private
notes, fence or infrastructure credential. SSE reauthorizes each replay, supports
Last-Event-ID, sends heartbeat comments, caps active streams and closes on terminal state,
session revocation, disconnect or storage failure. Event IDs increase within each job;
terminal events require a resource refetch. The frontend still displays the saved draft
workflow because supplier-facing jobs have not been enabled.

## Operator commands

The existing worker can be updated using the explicit credential-free source archive and
[safe installer](../scripts/setup_supervisor.sh). Its config and server keys remain under
/var/lib/latch; the local client cert/key remain in ignored private/supervisor-tls. The
channel certificates expire after 30 days and require operator renewal before then.
Do not copy the worker CA key or server key into the application or browser image.

From the project root, start the restricted tunnel and the separate runner:

```bash
python3 scripts/worker_host.py --tunnel
.venv/bin/python -m services.runner.jobs
```

Use separate terminals. These commands do not enable source inspection, admit a profile
or populate buyer data. Stop the foreground processes with Ctrl+C; leases and supervisor
cleanup remain authoritative after a runner stops.

The actual checks use the installed technical documentation profile. They perform network
calls and interruption operations on the dedicated project worker:

```bash
PYTHONPATH=. .venv/bin/python scripts/check_supervisor.py
PYTHONPATH=. .venv/bin/python scripts/check_runner.py
```

A separate operator diagnostic stops its Python executor with SIGSTOP during an actual
running timeout container; the independent timer removed it after its real 12 second
diagnostic lease. This proves cleanup did not depend on the stopped executor watchdog.

The runner check creates only an isolated test schema, records its exact recovery IDs,
kills its exact runner process during an observed browser task, waits for actual lease
expiry, reconciles and recaptures under a new fence. It drops its exact schema on success.
Recovery notes and captured bytes remain ignored under var. Public nonsensitive evidence
is recorded in [P4 status](evidence/P4_STATUS.json).

Supplier adapters, permitted terms completeness, actual buyer consent and the enabled
inspection/review interface remain pending. No supplier price or successful release is
inferred from these infrastructure checks.
