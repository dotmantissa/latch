# Implementation roadmap and work packages

This roadmap defines finish gates. The provider independent foundation, identity and saved worksheet are implemented; their checks are described in [LOCAL.md](LOCAL.md) and [worksheet evidence](evidence/WORKSHEET_STATUS.json). PostgreSQL backup/restore and release constraints remain deferred alongside the live workflow. Actual Vultr text/tools/image and isolated worker infrastructure are verified in [worker evidence](evidence/WORKER_STATUS.json). Private mTLS supervision, durable Postgres jobs, fenced recovery and stored SSE are implemented; [P4 scope](SUPERVISOR.md) separates technical infrastructure checks from pending supplier inspection, review and release acceptance. Root TASKS.md remains the one local recovery checklist and is not a deliverable to commit. The user now authorizes repository creation, a commit for each implementation step and push to https://github.com/dotmantissa/latch. Use only dotmantissa <negativemantissa@gmail.com> as author/committer with no coauthor trailer. Deployment and submission require separate authorization.

Package order follows dependencies, not page decoration. Each package finishes with its named evidence and a TASKS.md update. The user explicitly authorizes deferring live P0 to implement the provider independent packages and using Neon Postgres instead of SQLite. Frontend work must begin from the recorded design roll/token plan and use real API data; an empty/error state is preferable to fabricated content.

## P0. Resolve real source and environment feasibility

Dependencies: approved architecture and access to a real supported buyer/source task. Confirm the buyer actually uses no-login publicHTML offers, exact stock/quantity/delivery terms and a three-item scope. Collect accessible source URLs/consented evidence without unauthorized outreach. Record unknown support explicitly. If essential information is only in private PDF/email/portal, stop and resolve scope; do not substitute fictional pages.

Runtime scaffolding and Git initialization are complete under the user authorization. Install Node 24LTS and compatible exact frontend packages, Python 3.13 backend, fixed SQLite runtime and pinned browser image. Read installed/current docs, save locks, record version output. Validate real Vultr key access with a text/tool schema call and screenshot input. Verify non-root browser/gVisor/seccomp/CPU/memory/time/egress/cleanup on the actual worker. No alternate provider or network mock.

Finish evidence: real source compatibility record, dependency manifest, authenticated model usage, actual screenshot capture, positive allowed fetch, denied metadata/private fetch, actual timeout and cleanup. This gate remains a hard dependency for source/model/worker features. Domain, identity and persisted draft implementation may proceed under the explicit deferral authorization.

## P1. Contracts, domain and storage foundation

Create typed models from CONTRACTS.md, migrations and strict numeric/time/source validators. Implement versioned request/items/source tables, owner scoping, immutable comparisons/reviews, approval/release uniqueness and events. Domain functions are pure and cannot import model clients. Use pooled Neon Postgres application connections and direct transactional migrations with version checks, immutable triggers and row locks. Implement canonical packet/content hashing with versioned normalization and explicitnulls.

Create error taxonomy and generate OpenAPI/TypeScript types from actual server schemas. Add rule assertions using real captured/independently checked supported inputs, including an incomplete offer and pack conversion if observed; do not fabricate a successful live task to satisfy coverage. Mathematical boundary assertions are allowed as unit checks, clearly separate from live acceptance.

Finish evidence: migration forward/restore on actual Neon database, strict validation rejection, null-vs-zero behavior, deterministic hash across process restarts, unique release constraints and cross-request reference denial. No broad in-memoryfake database used to claim durable behavior.

## P2. Identity, application shell and brand

Implement account provisioning throughTTY, Argon2id login, cookie sessions, reauth, CSRF/Origin and logout/revocation. Add owner checks to every resource route, SSE/export/artifact included. Use a real Neon database and actual HTTP login; no client-only auth flag. Rate-limit password work and queue creation.

Build React routes, CSS token/theme bootstrap, fonts/licenses, lucide icons and the actual provided mark/favicon assets. Create the persistent request rail/wide document stage/release seam, keyboard navigation, theme switch and meaningful empty/loading/error states. Route/title/copy entries must match COPY.json. Do not write fake requests to decorate the shell. Implement responsive fallbacks before adding complex evidence interaction.

Finish evidence: real sign-in/session expiry/reauth/logout, unauthorized direct URL denial, both themes without flash, true empty request list, logo/tab icons at actual sizes, keyboard navigation and320/390/1440layouts. Human visual review checks the design, not merely a green test.

## P3. Request worksheet and saved history

Implement list/detail/create/edit endpoints and frontend forms with3item/3source limits, exact specification/public-spec distinction, currency/budget/quantity/delivery validation and supported-profile admission. Save draft explicitly; display server acknowledgement. Use If-Match for edits, preserve versions and invalidate dependencies on material change.

Add source/quantity errors and no-feasible guidance in human copy. Keep unsaved local form separate from persisted status; warn on navigation without trapping user. Query/cache keys include owner/request/version. No autosave claim before actual persistence.

Finish evidence: save/reload in another real browser tab, edit conflict, invalid source rejection, expected deadline/timezone serialization and cross-owner denial. A refresh cannot lose a saved draft or silently duplicate creation after a dropped response.

## P4. Supervisor, capture and real progress

Implement private mTLS taskAPI, fixed job profile, artifact quarantine and container lifecycle. Create durable runner leases/fencing/heartbeat/cancellation and restart sweeping. Add network proxy/firewall policy, pinned browser, independent watchdog and bounded storage/logs. No arbitrary image/path/flag/URL eval. Public API never fetches source URLs itself.

Implement supported source adapters with explicit main/terms regions, readiness, capturedURLchain, content projection and completeness. Required content beyond caps becomes unsupported/partial. Store capture intervals and cleanup evidence. Wire actual status events to SSE replay/resume; model reasoning text is not a progress feed.

Finish evidence: actual supplier capture, permitted terms navigation, streaming status from stored events, cancel/timeout cleanup, runner restart, old fence rejection, worker unavailability and no host/private-network access. No routing mock or fabricated browser cursor/video.

## P5. Extraction and evidence-led review workbench

Implement typed public-only model context, bounded page/region/terms tools, structured extraction, source span checks and vision correspondence call. Record prompts/model/schema versions and actual usage privately. Schema repairs stay bounded; no model authority modules available. Inconsistent/missing terms stay unknown/disputed.

Build comparison ledger and evidence pane with crop/zoom/text attribution, field-state feedback, confirm/correct/dispute with reasons, original-value history, critical-review count and focus restoration. Use actual captures and API state. Recompute via domain rules after review; only feasible complete reviewed offers can be selected. Unknown/incomplete totals are textual, never zero. Mobile supplier tabs retain units and warnings.

Finish evidence: a human reviews a real supported source packet, checks/corrects fields and obtains matching deterministic totals. Inspect exact screenshot/source ranges. Test unknown terms and wrong-item/quantity basis where encountered; do not label model agreement as source truth. Count review/correction effort.

## P6. Approval, source diff and durable release

Implement server-constructed canonical approval/expiry, recent reauth, selection/version preconditions and revoke behavior. Build approval summary dialog and the stateful latch seam. Never show approved until the server persists it.

Implement asynchronous idempotent release attempt, all-source fresh capture, deterministic content diff, stale/unavailable/changed outcome and version invalidation. Implement short atomic final transaction with session/currentversion/approval/freshness/fence checks and unique receipt. Handle response loss with authorized lookup. No network call in transaction and no alternative fake success path.

Build real diff route with old/new evidence, changed total/eligibility, preserved earlier approval, required new review and fresh approval. Source removal/expiry/profile changes create new reviewed versions. Released state is based on durable receipt only. If no actual supplier revision is observed, record revision detection as unverified; do not edit our internal data and call it external discovery.

Finish evidence: actual approved/rechecked source set and one durable internal release, duplicate submission same receipt, concurrent edit/revocation stops commit, expired approval/freshness denied, unavailable source fails closed, restart-before/after-commit behavior. Real source revision evidence only when observable; security transition assertions may test pure domain preconditions but are not supplier-world evidence.

## P7. Receipt, export, retention and operator recovery

Implement immutable receipt page and PDF/JSON/manifest packet export using an offline bounded renderer, escaped templates and authorized attachment delivery. Hash exported bytes. Add private artifact ownership, request archive, explicit retention/deletion behavior and consistent encrypted backups/restores. Include the Latch mark and scope statement across receipt/export. No external source URL access while renderingPDF.

Finish evidence: real release lookup after restart, download hashes/content, no raw secrets/prompt/cookies/paths in packet, other-owner denial, backup/restore and compatible rollback plan. Export failure does not create/repeat a release.

## P8. Live evaluation and interface refinement

Run the real acceptance matrix at all required widths/themes/reduced motion with actual services/sources. Measure critical errors, wrong decisions, completion/abstention, human correction/review time, full task latency and paid usage. Compare with an actual manual/spreadsheet workflow using the same sources. Preserve adverse outcomes and consent boundaries.

Run scoped actual isolation/authority/resource probes on the deployed worker. Model refusal and broker enforcement are separate observations. Do not weaken policy to make a screenshot pass. No mocked API, sampledata fallback, prerecorded browser success or synthetic baseline participants. A missing outcome remains unverified.

Refine layout/copy from observed friction: evidence discoverability, pack units, missing-line explanation, version changes, stale terms and mobile action accessibility. Keep the five design decisions; fix usability without reverting to a generic card kit. Ensure no emoji/em dash/unnecessary hyphen in owned copy/README/title/accessibility strings, and no bogus claim in counters/status.

Finish evidence: acceptance manifest with commands/results/actualtimestamps, video/screenshot review, zero known critical unsafe releases in the finite tested scope and useful completed tasks. An all-abstention product does not pass.

## P9. Deployment and submission preparation

Only when deployment is authorized: harden actual Vultr control/worker, deploy exact audited builds, confirm TLS/DNS/data retention and verify actual public-entry/protected-workspace flows. Publish no source/customer secrets or private historical artifacts. README describes only implemented behavior, real limitations and reproducible setup. Prepare actual video/containment clip andPDFslides with no simulation. Check event form, remote prize eligibility and any remaining user-owned account/terms fields.

Git creation, commits per implementation step and push are now explicitly authorized by the user. Submission remains unrequested. No coauthor trailer or alternative author is permitted.

## Dependency graph and cut lines

P0→P1→P2/P3→P4→P5→P6→P7→P8→P9, with visual shell work after token plan and alongside contracts only under the explicit deferral authorization, with live source actions disabled until the real source spike passes. Keep one complete real vertical path ahead of optional refinements. No agent delegation is requested by this document.

If source fit fails, revise scope before implementation. If model adds no value, reassess competitiveness. If hardened browser fails, resolve/choose a verified permitted boundary; do not silently disable sandboxing. If recapture is not reliable, call the result a captured-term review tool and downgrade claims; do not hide a missing core feature. If time is constrained, cut public marketing detail and optional export formats before critical review, auth, source freshness, atomic release or isolation.

The earlier48hour estimate was unmeasured. Track actual effort afterP0 and reforecast; never call this full package guaranteed in48 hours. Planning detail does not make empirical work free.
