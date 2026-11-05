# Data, API and worker contracts

This is the detailed contract for [ARCHITECTURE.md](../ARCHITECTURE.md). The identity, profile admission and versioned request API are implemented. Private job supervision, durable leases/fencing and SSE replay are implemented as described in [SUPERVISOR.md](SUPERVISOR.md). [Captured evidence](EVIDENCE.md) and [individual review commands](REVIEWS.md) have implemented APIs. The review workbench, approval, release and export contracts below remain implementation instructions. See LOCAL.md for the available workflow. Display text comes from [COPY.json](../COPY.json). Never return internal secrets or infrastructure details in public errors.

## Representation rules

IDs are server-generated UUIDv7/UUIDv4 opaque strings; choose one library and pin it. Human request references are a separate nonauthorizing sequence, such as LCH plus a numeric suffix, not a security identifier. Store UTC timestamps as integer epoch milliseconds and serialize ISO8601Z strings. Money is integer cents, quantities/pack sizes integers, USD only, with bounds from the architecture. Required deadline stores UTC instant, requester timezone and the local entered value/basis.

Canonical hash input has `schema_version`, deterministic sorted keys, integer cents, explicitnulls and UTC strings. Do not hash a pretty-printed UI string or generated description. Source order is canonicalized by profile ID, profile version and canonical URL; material line order by stable required item key. The worksheet preserves entered order separately. An immutable comparison/policy/hash version is stored with each approval. Specify hash algorithmSHA-256; do not call this a cryptographic signature or independently verifiable source truth.

API accepts application/json with2 MiB request body cap; source text/artifacts travel through the private worker protocol, not a public upload endpoint. Strict schemas reject unknown fields on mutations. Mutations require authenticated owner, CSRF, Origin, version precondition and idempotency where stated. URL validation/profile admission is server-owned. No inlineHTML is accepted as a supplier source.

## Storage model and migrations

Use the supplied Neon Postgres database with a dedicated latch schema. Application queries use its pooled TLS connection; migrations use the corresponding direct endpoint. Disable automatic prepared statements and set search_path, statement_timeout and lock_timeout within each transaction for pool compatibility. Migrations are numbered and checksum verified, serialized by an advisory transaction lock, and run explicitly before app startup. Refuse newer or altered schemas. Test new migrations in an isolated environment and retain a recovery point before changing populated data. The initial schema is new and empty; it does not alter public tables.

| Table | Required columns and constraints |
| --- | --- |
| users | idPK, username unique normalized, display_name, password_hash Argon2id, active boolean, created_at, password_changed_at; email optional/unverified |
| sessions | idPK, token_hash unique, user_idFK, created_at, last_seen_at, absolute_expires_at, reauthenticated_at, revoked_at nullable; never plaintext token/password |
| requests | idPK, owner_idFK, current_version integer, created_at, updated_at, archived_at; index owner+updated |
| request_versions | request_idFK, version, name, currency, budget_cents, required_by_utc, timezone, delivery_basis, content_hash; compositePK(request_id,version), immutable |
| required_items | idPK, request_id+versionFK, stable_item_key, specification, public_specification, required_units, ordered_position; unique request-version+stable_item_key |
| supplier_sources | idPK, request_id+versionFK, label, canonical_public_url, profile_id+profile_version, supplier_key; unique canonical URL per request-version |
| source_profiles | id+versionPK, reviewed exact origin/path/asset policy, extraction region definition, semantic projection version, active/expiry; no credentials |
| captures | idPK, source_idFK, job_idFK, attempt_id, capture_started_at/completed_at, observed URLs/statuses, raw hashes, content_hash, completeness, incomplete_reason, profile_version; immutable |
| artifacts | idPK, owner_idFK, capture_id optionalFK, storage_object_id, sha256, mime, bytes, width/height, redacted flag, created_at, retention_until; no public URL/filesystem path in API |
| extraction_versions | idPK, capture_set_hash, schema/model/prompt versions, created_at, validity; immutable, source captures referenced through junction |
| fields | idPK, extraction_idFK, source_idFK, required_item_key nullable, kind, typed_value_json, support_state, source_span, region_artifact_id, ambiguity_reason; unique extraction+source+item+kind |
| field_reviews | idPK, field_idFK, reviewer_idFK, action confirm/correct/dispute, corrected_typed_value nullable, reason, evidence_reference, created_at, review_version; append-only |
| comparisons | idPK, request_id+versionFK, extraction_idFK, review_set_hash, policy_version, sources_hash, derived_terms_hash, result_json, ready boolean, created_at; immutable |
| selections | request_idPKFK, comparison_idFK, selected_source_idFK, selection_version, changed_at; update only through owner command, invalidates approval |
| approvals | idPK, owner_idFK, request_idFK, comparison_idFK, selected_source_idFK, packet_hash, policy/profile hash, approved_at, expires_at, revoked_at/reason; immutable approved payload |
| jobs | idPK, owner_idFK, request_idFK, type inspect/recheck/export, state, requested_version/hash, attempt_no, lease_owner, lease_until, fence_token, cancel_requested_at, deadline_at, safe_error_code; durable |
| attempts | idPK, job_idFK, attempt_no, worker_task_id, fence_token, started_at, finished_at, outcome, cleanup_status, model_usage_json, manifest_hash; unique job+attempt_no |
| recheck_manifests | idPK, approval_idFK, attempt_idFK, old/new capture maps, fingerprint_result, earliest/latest capture times, payload_hash; immutable and references every decision source |
| release_attempts | idPK, owner_idFK, approval_idFK, job_idFK, state, idempotency_key, intent_hash, release_id nullable; unique owner+idempotency_key |
| releases | idPK, owner_idFK, request_idFK, approval_id uniqueFK, packet_hash, immutable_payload_json, recheck_manifest_idFK, created_at; only release transaction can insert |
| events | id integerPK, owner_idFK, job/request/release IDs, kind, safe_payload_json, at; owner+job+id index, monotonic per stream |
| audits | idPK, owner_idFK, action, subject_id/version, old/new content hashes, actor_type human/service/model_proposal, at, correlation_id; no raw secret/prompt |
| idempotency | owner_id, route_scope, key, intent_hash, resource_id/status, created_at, expires_at; unique owner+scope+key |

Never delete/rewrite captured/approved values to correct the current view. Insert a new version/review/comparison. Mutable current pointers are updated transactionally. Reviews depend on exact field/capture versions. Reusing them after source change is forbidden unless the user explicitly rechecks the new field through a new review row.

Use composite foreign keys or explicit transactional ownership checks to prevent cross-request references. Validate that comparison.request_version and source-set match approval, selection belongs to comparison, and all manifest captures match approved source profiles. Database constraints protect uniqueness; domain code protects these semantic relations. Require tests that intentionally submit references from another request/owner.

## Resource state

Request UI status is derived from current immutable resources, not a model enum. States: draft, queued, inspecting, needs_review, ready_for_approval, approved_version, rechecking, source_changed, source_unavailable, released. Incomplete/infeasible are comparison outcomes with reasons, not permanent request failure. Failed/timed_out/cancelled/expired apply to jobs or approvals and must not erase the saved request.

| Command/event | Preconditions | Persisted effect | UI next state |
| --- | --- | --- | --- |
| Save draft/edit | Owner, matching current version, valid inputs | New immutable request version/current pointer; old approval revoked | draft or needs_review |
| Inspect | Supported source set/current version, queue limit | Durable inspect job/event | queued then inspecting |
| Capture complete | Active attempt/fence, valid source/profile/artifacts | Captures/extraction, derived proposed comparison | needs_review |
| Confirm/correct/dispute field | Owner, matching current field/version, source shown | New review row, recalculation, invalidate approval | needs_review or ready_for_approval |
| Select offer | Complete feasible reviewed current comparison | New selection version, invalidate old approval | ready_for_approval |
| Approve | Current reviewed selection, recent reauth, no critical unknown | Approval payload/hash+expiry and audit | approved_version |
| Release request | Active owner approval, exact current intent, idempotency | Durable release attempt/job | rechecking |
| Source changed | Valid active recheck with changed content | New captures, diff, approval revocation | source_changed then needs_review |
| Source unavailable | Failed/partial/late required recapture | Safe error+new evidence, no receipt | source_unavailable |
| Recheck unchanged+atomic checks pass | All invariantsI1–I8 and current-time delivery feasibility | One release+immutable receipt/event | released |
| Clock/session/version/expiry conflict | Failed commit precondition | No release; precise error | requires sign-in/review/recheck |
| Cancel | Active job, owner | Cancellation intent; finalize only after cleanup | saved request plus cancelled job |

A released record is immutable. Reopening work makes a new request version and later new approval. Never “unrelease” history by overwriting it.

## Public HTTP surface

All paths below are under/api/v1 except health. Return a JSON envelope with data/resource_version on success. Errors have code, message_key, field_errors, retryable, correlation_id and current_version when authorized. No stacktrace, full provider response, raw URL token or infrastructure address. Validate Content-Type/Accept. Unknown owners receive404, not an existence oracle.

| Method and path | Request / response | Required behavior |
| --- | --- | --- |
| GET /health/live | Process alive | No DB/model network call; public minimal status |
| GET /health/ready | DB/schema/runner freshness aggregate | Public healthy/degraded/unavailable only; sensitive diagnostics private |
| POST /auth/login | username,password→session cookie/user/CSRF | Origin check; generic error; session rotation; never log body |
| GET /auth/session | user,expiry,CSRF,reauth freshness | no-store; cookie remains HttpOnly; csrf derived server-side |
| POST /auth/reauth | password→new freshness/session rotation | Rate limit; current user only; token never in model/job |
| POST /auth/logout | empty→204 | CSRF, revoke session, expire cookie, terminate streams |
| GET /source-profiles | admitted source labels/origin support | No infra settings; owner session; operator-only write outside public API |
| GET /requests | cursor/limit≤50→authorized summaries | No seeded/demo rows; server pagination; exact unknown total handling |
| POST /requests | name/USD decimal budget/deadline+local basis/items/sources→201 | Idempotency; strict bounds; create immutablev1 |
| GET /requests/{id} | current versions/status/reasons | Owner-scoped ETag; no unauth source values |
| PATCH /requests/{id} | complete edit or explicit patch→new version | If-Match required; preserve old version; revoke dependent approval |
| POST /requests/{id}/inspections | current_version→202job | Idempotency; deny unsupported source/profile; real work queued |
| GET /jobs/{id} | phase/status/error/cleanup | Owner; no full tool logs or secrets |
| GET /jobs/{id}/events | SSE Last-Event-ID | Owner/no-store, replay persisted events, heartbeat; no fabricated updates |
| POST /jobs/{id}/cancel | current job version→202 | Idempotent, actual supervisor cancellation/cleanup |
| GET /requests/{id}/comparisons/{cid} | fields/results/review counts/source ages | Owner, immutable comparison, no model authority flags |
| POST /fields/{id}/reviews | expected version,action,value/reason/evidence→201 | CSRF/If-Match, strict type, new review and comparison version |
| POST /requests/{id}/selection | comparison/source/selection version→200 | Only feasible current source; revoke prior approval |
| POST /requests/{id}/approvals | comparison/selection version→201 | Recent reauth; server constructs packet;10min expiry |
| DELETE /approvals/{id} | revocation reason→204 | Owner; idempotent; invalidate in-flight release via commit checks |
| POST /requests/{id}/release-attempts | approval/version+key→202attempt | Fresh recapture job, no instant optimistic receipt |
| GET /release-attempts/{id} | state,diff/new comparison or release_id | Owner; recover lost response; terminal requires authoritative fetch |
| GET /requests/{id}/changes/{cid} | old/new term evidence and reasons | Owner; source fingerprint change cannot be dismissed by model |
| GET /releases/{id} | immutable receipt/manifest | Owner; hash/version/capture times included |
| POST /releases/{id}/exports | format packet→202job | Owner/idempotent; generate from immutable source record |
| GET /exports/{id} | state/download artifact | Owner; export job failure never fabricates a file |
| GET /artifacts/{id} | bounded raster/attachment stream | Owner each request; no path traversal/public permanent link |
| POST /requests/{id}/archive | expected version→200 | Saved history retained per explicit retention policy |

409 codes: VERSION_CHANGED, IDEMPOTENCY_MISMATCH, APPROVAL_REVOKED, SOURCE_SET_CHANGED, SELECTION_NOT_READY, ALREADY_RELEASED with authorized receipt lookup.412 VERSION_PRECONDITION for stale If-Match.422 validation/UNSUPPORTED_SOURCE/UNSUPPORTED_TERMS.401 SESSION_REQUIRED/REAUTH_REQUIRED;403 CSRF_ORIGIN_REJECTED.429 RATE_LIMIT/QUEUE_LIMIT;502 PROVIDER_UNAVAILABLE;503 WORKER_UNAVAILABLE;504 INSPECTION_TIMEOUT. Provider errors are categorized, never copied verbatim.

Mutating requests use `Idempotency-Key` where listed, stored with owner+route+canonical intent hash. Draft intent keys are retained until an operator retention policy is implemented, and cannot silently perform another command after 24 hours. Future job TTL is 24 hours; approval→release uniqueness retained permanently with the release record. Returning an old key's result never crosses owner scope. HTTP GET never approves, releases or starts paid model work.

## Worker and model protocol

Private supervisor accepts a request with task_id, job_id, attempt_id, fence_token, profile_version, allowed URL tokens, typed action list, deadline, public item specs and output limits. It rejects arbitrary shell/image/path/runtime/security/network flags and fields absent from schema. Request auth is mTLS between trusted hosts, not a token passed into the sandbox. Limit task body 256 KiB; use server-generated spool IDs for bounded trusted transport.

Supervisor task endpoints: POST/private/tasks creates one task idempotently, GET/private/tasks/{id} returns safe status, POST/private/tasks/{id}/cancel requests exact task termination, GET/private/tasks/{id}/outputs streams a bounded manifest/artifacts. None are internet accessible. Poll/control endpoints verify fence token and caller certificate; an old attempt cannot submit artifacts to a new task.

Model tools: inspect_page(page_token), inspect_region(capture_id,region_token), open_terms(approved_terms_token), propose_fields(typed_fields), request_clarification(public_question). Page/region/token references must belong to this job. No eval, arbitrary URL, fill, submit, shell, browser-cookie, budget, human-review, approval or release tools. Arbitrary model text outside a supported tool/schema is not executed.

The control model receives only public approved specifications/captured public source content. All source text is explicitly untrusted input; prompts do not constitute a boundary. Output fields contain source evidence references and ambiguity. Results are schema-validated before any state change; a schema repair prompt can request formatting only, never expand authority. Max2repairs; fail visibly afterward.

Worker result manifest includes actual task/attempt/fence, image/runtime digests, capture URL chain/status/times, completeness reasons, text span dictionary, raster metadata/hashes, observed limits, exit/timeout/cleanup and artifact enumeration. Supervisor validates names as relative opaque IDs, refuses symlinks/hardlinks/unexpected entries and streams approved bytes; control revalidates. No task-generated “verified safe” flag is trusted.

## Artifact/export contract

Evidence is a raster image plus UTF8text and metadata; no supplier HTML/SVG is served as app-origin content. Raster maxwidth4000/height16000 and declared byte cap, validated in a separate bounded sanitizer process/sandbox; decompression bombs cannot run in the API process. Unknown files go to quarantine and are not downloaded as trusted results.

Packet export contains an immutable receiptJSON, human-readable receiptPDF produced from escaped trusted templates in an offline bounded renderer, source indexJSON, consented raster captures and README-style plain text scope. No network fetch while rendering/exporting. Exclude raw prompt transcripts, cookies, credentials, private runtime paths and unrelated annotations. Owner explicitly downloads; sharing is not automatic. Content-Disposition attachment with generated safe filename, nosniff/no-store, no sensitive title in public URL.

A generatedPDF is only an alternate view of the durableJSON record. Export failure leaves the release valid and retryable, never creates another release. Store output hashes and verify download bytes against them.

## Implemented private workflow additions

The strict generated contracts now include immutable raster correspondence, complete
comparison signatures, explicit selection revisions, canonical expiring approvals,
all-source release attempts/diffs, commit-guarded receipts and hashed exports. See
[workflow](WORKFLOW.md), [correspondence](CORRESPONDENCE.md) and [recovery](RECOVERY.md)
for the actual routes, limits and observed scope. Migrations001–004 remain immutable;
new functionality uses additive numbered migrations. Supplier-world/buyer acceptance
remains distinct from isolated security assertions.
