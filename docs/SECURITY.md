# Trust boundaries, secrets and operations

Implements the invariants in [ARCHITECTURE.md](../ARCHITECTURE.md). These are required controls and future verification steps. The identity and saved request controls have local HTTP and Neon integration checks. Actual worker infrastructure and Vultr capability observations are recorded in [worker evidence](evidence/WORKER_STATUS.json). Supplier accuracy, durable supervisor recovery, release and deployment controls still require their own live evidence.

## Threat model and data classes

Untrusted: supplier JavaScript/DOM/text/images/redirects, model/tool output, user-entered source URLs, worker artifacts, stale browser submissions and exported file consumers. Trusted with limited authority: API authentication/policy, transactional release code, runner orchestration, supervisor and egress proxy. A browser context, model response or UUID never becomes an authorization principal.

Protected assets: buyer requests/identity/notes, approval authority, release history, model/provider and mTLS credentials, host/kernel resources, other sessions and controlled spend. The application cannot establish the truth of a supplier statement or protect a fully compromised administrator/host. Treat operator access as a privileged action, not part of an anonymity guarantee.

Classify public source material, private buyer data, authentication secrets and infrastructure secrets. Only public approved specification/source content goes to the browsing model. No request owner/budget/notes in that context. Data sent to inference is explicitly disclosed before inspection. Reject token-bearing or authenticated source URLs; do not “redact” their tokens then pretend the URL still works. Real buyer evidence may be retained/shared only under consent.

## Secret inventory and handling

| Secret | Trusted location | Explicitly forbidden destinations |
| --- | --- | --- |
| Vultr inference key | Control runner service credential file, mode 0600 | Frontend bundle, Vite variables, model prompt, browser/container, logs/packet/source repository |
| Vultr provisioning credential | Operator secure store only; not required in normal runtime | API, runner task, CI artifact, runtime image or client |
| API CSRF/HMAC service key | API credential file0600 | Public config, URL/query, model or worker |
| Password hash | Private Neon Postgres users table | Logs, API response, export, screenshot |
| Session raw token | Secure HttpOnly cookie only | localStorage, generated report, worker/model, URL |
| Supervisor client/server key | Trusted control runner and worker service credential files | Container mounts/environment, browser/CDP, support logs |
| Backup encryption key | Operator-managed separate secure storage | Same backup archive, source/deployment bundle, public media |

No actual secret is written in .env.example, architecture examples, checklist or public docs. Provision with service credentials or secure files, not command-line arguments or shell history. Process logs must not dump environment/header/body. Never pass a provisioning token simply because the worker runs on Vultr; runtime execution does not need one.

At implementation start create a typed environment schema with placeholders documented by name only: LATCH_PUBLIC_ORIGIN, LATCH_DATA_DIR, LATCH_WORKER_URL, LATCH_INFERENCE_BASE_URL, LATCH_MODEL_ID and credential-file paths. Only public presentation values can use VITE_*. Secrets are read server-side at startup from paths, never returned to frontend config. Missing credentials cause a clear unavailable state; no silent demo mode or alternate provider.

Apply source/bundle/artifact secret scans using configured secret values without printing matches; scanners report file/offset/class only. Add pattern checks for private key blocks, provider tokens and raw session headers. Verify tracked/deployment asset lists and exported packet contents before publication. Ignore rules are a guardrail, not proof a secret is absent. On suspected leak: revoke/rotate first, then clean affected data/history and verify logs/backups; never merely hide the string in UI.

## Authentication and browser session

Provision named accounts through an interactive operator command reading password from TTY, never argv. Use Argon2id with per-user random salt; initial parameters64 MiB,3 passes,parallelism 1, then benchmark a bounded acceptable login cost. Store algorithm/parameters with hash. Limit login hashing concurrency 2 and rate by account/IP to prevent a memory denial of service. Username normalization is stable; generic login failure avoids account enumeration.

Issue random 32 byte token after login, store SHA-256(token), rotate on login/reauth, and revoke on logout/password change. Cookie: __Host-latch_session, Secure, HttpOnly, SameSite=Lax, Path=/, no Domain. Session idle limit 2 hours, absolute 12 hours, approval step-up freshness 15 minutes. No fake remembered login or browser bearer storage.

For authenticated mutations require same allowed Origin, JSON content type and X-CSRF-Token. Derive CSRF value from HMAC(API secret,raw session token plus version), return via no-store session endpoint, keep only in memory; constant-time comparison server-side. Login additionally validates Origin/content type without needing an existing session. Do not enable permissive CORS. SameSite is defense in depth, not a replacement for Origin/CSRF checks. SSE is read-only, authorized before stream and periodically during it; logout closes user streams.

All artifacts/requests/approvals/rechecks/exports include owner checks at query time. Cross-request references are checked even for the same owner. A shared evaluation account must not contain private buyer data; provide isolated accounts with explicit consent. Release identity is the provisioned requester, not verified corporate/legal purchasing authority. [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

## Browser isolation and egress

The supervisor is private, authenticated and host-administered; the public app has no Docker socket/control. Pinned image contains only required Chromium/Playwright/runtime dependencies, a non-root user, compatible seccomp and verified gVisor runtime. No cap-addSYS_ADMIN, privileged mode, host IPC/network/PID namespace or no-sandbox rescue in production. Use isolated shared-memory allocation with a bounded explicit size, not host IPC. Verify Chromium actually enables its sandbox under the selected runtime.

Starting limit per task:1.5 CPU,3GiBRAM, memory-swap equal to memory,256 PIDs,90second capture watchdog, bounded10 MiB accepted output/source, isolated temporary storage with a hard size cap and64 KiB retained log. Global one job until performance proves headroom. The exact flag support must be tested with gVisor; stop readiness if controls are ineffective. Resource settings are supervisor-chosen and cannot be overwritten by model/user payload.

Only an external proxy can connect to configured public origins/paths/ports; direct task egress is denied at the host/network layer. Browser settings are not the sole boundary. Block127/8, RFC1918, link-local/metadata169.254/16, IPv6loopback/link-local/unique-local/reserved, IPv4-mapped variants, malformed/alternate encoded addresses, unapproved schemes and redirects. Resolve/pin at connect and verify TLS hostname. Proxy must deny CONNECT tunneling to arbitrary ports and avoid becoming a general network relay. Block QUIC/UDP/WebRTC, arbitrary DNS and WebSockets unless an explicit profile later proves a legitimate need.

A public allowed origin can still receive data in a path/query. Therefore browser/model task receives no private buyer/session data and only server-issued URL tokens; arbitrary URL/field text is rejected. No authenticated supplier profile in MVP. Capture scopes include terms/exclusions and cannot be dynamically narrowed by a page instruction. [OWASP SSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

Pin Playwright and installed browser revisions together. Default Playwright images use root and are not a finished production sandbox for untrusted sources; build/test hardened image/runtime deliberately. gVisor still needs network/cgroup/service defenses. [Playwright guidance](https://playwright.dev/python/docs/docker), [gVisor security](https://gvisor.dev/docs/architecture_guide/security/)

## Input, artifact and UI defenses

Strict schema/byte/enum/range/recursion limits apply before processing. No eval, shell interpolation, arbitrary Python/JS generation, source URL fetch in API, HTML template interpolation or page-defined tool execution. Supplier JSON/HTML/scripts are never trusted app configuration.

Worker output is quarantined; check relative opaque names, reject symlinks/hardlinks/duplicate/path traversal, validate declared and actual size/hash/type, and sanitize raster dimensions in a bounded separate process. API does not decode adversarial images. Serve evidence with nosniff, restrictive content types/no-store and authenticated ACL. Do not inline supplierHTML/SVG. Reports use escaped owned templates in an offline renderer; export is an attachment, not browser-executable HTML. CSV formulas are neutralized if CSV is later supported.

CSP starts restrictive: default-src self, script-src self plus exact theme-bootstrap hash, style-src self with a reviewed strategy for library inline styles, img-src self data only if needed for bounded local preview, font-src self, connect-src self, frame-ancestors none, base-uri none, form-action self, object-src none. No unsafe-eval or wide wildcard provider domains in frontend. Choose accessible primitives/CSS so the implemented policy is verified, not copied into docs while the UI breaks. Public supplier originals open with noopener/noreferrer in a separate context.

Set Referrer-Policy no-referrer, X-Content-Type-Options nosniff, secure cookies and HSTS after HTTPS verified. Redact request names/amounts from title/public social metadata. Logs use safe correlation/job IDs, typed outcomes, durations and costs, never passwords/cookies/keys/raw prompts/full sensitive URLs.

## Deployment procedure

1. Confirm real supported source task, event/account eligibility, current plan pricing and inference credit coverage. Do not provision on the strength of an assumed credit. No deployment is authorized in this planning task.
2. When implementation/deployment is authorized, select control+worker in a suitable Vultr region/private network; generate credentials securely. Restrict SSH to operator key/source; close password/root login, patch OS and record image/build IDs.
3. Configure firewall: control public80/443 plus operatorSSH; API loopback; worker supervisor private mTLS from control only; proxy public egress only; task cannot reach control/metadata. No public remote browser or Docker API.
4. Build pinned dependencies/images with lockfiles; scan contents; test non-root Chromium/gVisor/limits. Record runtime/image/browser versions and SBOM. Use direct Neon TLS access for checksum verified transactional migrations.
5. Mount private persistent data, mode 0700; load server secrets from0600service credentials. Apply migrations once and provision named requester accounts without shell-history secrets.
6. Run API, runner, supervisor and proxy under managed services with restart policy, resource budgets and graceful termination. Add orphan-sweeper/reconcile timer. Caddy serves built frontend and proxies API/SSE without buffering; persistent certificate storage and correct DNS are prerequisites.
7. Verify readiness without exposing infrastructure: DB schema/runner heartbeat/worker reachability and last successful model capability check. Do not make public readiness trigger a paid model call on every request.
8. Run actual authenticated journey, cross-owner denial, source change discovery where a real revision is available, fail-closed recheck and artifact download checks. Persist observed manifests privately. Keep source/site policy enabled during recording.
9. Audit production bundle for raw private data/secrets/localTASKS/instruction files/history. Publish only runtime/public docs/assets intended for judges; historical research and buyer evidence are not automatically public application assets.
10. Set cost/job caps, retention and teardown/continuing-host plan. Stop old images only after live acceptance and a recoverable previous release are known. Do not silently keep paid orphan VMs after the event.

## Recovery, backups and retention

Before changing populated Neon data, retain a project recovery point or consistent pg_dump using the direct connection. Confirm the actual Neon plan history window instead of assuming retained backups. Encrypt operator dumps and artifacts with separately managed keys. Restore to an isolated branch/database and verify schema, hashes, owner counts and release uniqueness before switching a running service. Backup/restore and receipt recovery remain future validation gates; the current migration verification covers fresh schema creation and transaction rollback only.

A deploy rollback is permitted only if binary/schema compatibility is explicit. Do not run an old binary against a new schema. New runner/supervisor reconciliation must fence old completions and clean only its job labels. A mid-release failure before commit leaves no receipt; after commit it recovers the same receipt by idempotency/approval identity.

Initial retention proposal: unreleased capture data7 days after last activity; public-source released packet30 days with an operator-configured review/extension; sessions expire/revoke; model usage/event metadata30 days without raw secrets. Confirm with the actual buyer before using private data. No compliance/immutable-forever claim. Display deletion/retention consequences; removing current UI history is not proof old backups were erased. Document backup expiry/key destruction policy.

## Operations and budgets

Observe queue age, job durations, source failures, review/abstention, model tokens/cost, rejected tools, attempt cleanup, runner heartbeat, disk space and database connection/lock failures. Initial caps:1activejob/user and global1; up to3 sources,6 pages,12 model decisions;10 inspect/recheck requests/user/hour; configurable daily paid-usage ceiling enforced before starting new model work. Provider bills can exceed estimates from images/reasoning; reconcile actual usage. A circuit breaker exposes a plain unavailable state rather than synthetic results.

Use safe operator-only diagnostics, no raw environment dumps. Incident actions: suspend new work, preserve minimal safe evidence, revoke exposed credentials if applicable, contain worker, restore/reconcile state, rerun the affected real acceptance path, then resume. Document both adverse and successful outcomes.

Current local limitation: the login limiter is bounded and process local. Run one API process until a shared throttle and queue limits are implemented. Secrets remain in private mode 0600 files. PostgreSQL transaction locks serialize owner commands and session revocation. Draft archive retains immutable versions and does not claim deletion.
