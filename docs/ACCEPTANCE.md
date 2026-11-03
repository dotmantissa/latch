# Real service acceptance and evidence plan

No test below has been executed by this planning package. It defines what later implementation must prove. No mocks, simulated buyers, fictional vendors, seeded success rows or prerecorded responses may stand in for the chosen live path. Historical synthetic arithmetic is not acceptance evidence. Read [ARCHITECTURE.md](../ARCHITECTURE.md) and [the roadmap](IMPLEMENTATION.md) first.

## Environments and truth labels

Local integration uses the actual localAPI/database, real browser and actual configured Vultr inference/isolated worker. Production acceptance repeats the path on deployed Vultr HTTPS. The app has no blockchain; record actual Vultr region, model ID, browser/runtime/image digest, source URLs/profiles and observed timestamps. No testnet/mainnet transaction is invented.

Owned security probes can test actual runtime enforcement with authorized malicious inputs. They must be labeled security tests, never real supplier/customer behavior. Unit calculations test rules only and cannot substitute for a real model/source/release run. An expected outcome is not a measured result.

Evidence status per case: planned, running, passed, failed, unverified or blocked. Passed requires actual observation and retained output; skipped/missing user/source access is unverified, never success. Each run records runID, build/version hashes, environment, actor consent, actual steps/commands, expectations, observed outcomes, safe artifact hashes and limits.

## A. Full product journey

| ID | Live action | Pass condition and evidence |
| --- | --- | --- |
| A01 | Sign in as a securely provisioned named requester | Actual cookie session, owner identity, CSRF/Origin, no browser bearer storage; invalid/expired session rejected |
| A02 | Create a real supported request and save | DB row/version; reload/second tab recovers exactly; no sample fallback |
| A03 | Inspect actual supported supplier origins | Real Vultr inference usage, real sandbox browser screenshots/terms, URL/profile/version/time and cleanup; truthful SSE |
| A04 | Review exact terms with the human operator | Every confirmed/corrected critical field links to actual source/capture; uncertainty remains visible |
| A05 | Calculate full basket | Independently checked item/pack/MOQ/shipping/tax/delivery terms match deterministic results; incomplete total isnull |
| A06 | Select and approve a feasible reviewed offer | Stored version-bound approval, recent reauth, exact total/conditions/scope/expiry; no supplier transaction claimed |
| A07 | Release triggers all-source recapture | Real new captures for each decision source, current time and profile; no HTTP cache substituting for check |
| A08 | Unchanged sources produce release | One atomic durable record, recheck freshness<=60s, approval<=10 min, matching owner/version/hash; actual receipt |
| A09 | Download packet and restart services | Owner-authorized actual bytes/hash, readable source references, record survives restart, no duplicated release |
| A10 | Observe a real supplier source revision and recheck | Actual source change discovered without editing internal quote; diff/invalidated approval/new review. Use a cooperating real source or observed public revision, not a fake fixture. Without available revision, mark unverified |
| A11 | Source genuinely unavailable during recheck | Request remains unreleased with explicit retry/stale-draft option; no fabricated recent-check time |

For A10, do not force an external change or contact a supplier without authorization. An authorized real source owner may change a genuine live offer; this is a real integration event, not an invented quotation. A pure domain assertion may verify rejection of a changed manifest, but must be reported separately from external discovery.

## B. Decision and authority invariants

B01 Missing required item: use an actual independently checked source where observable; never turn missing line into0cost or select incomplete offer. B02 Pack/MOQ conversion: independently recompute quantities and price basis; integer cents only. B03 Unknown tax/shipping/currency/availability/delivery basis stops readiness. B04 Claimed shipping date is not arrival; unknown business-day calendar is not silently converted. B05 Model/displayed total cannot replace rules output.

B06 A posted field confirmation/correction must reference current field/capture and actor; original extraction preserved. B07 Changed request/selection/profile/policy/review/source-set invalidates approval. B08 Confirming one field cannot confirm unrelated fields. B09 All-abstention behavior is reported as low completion, not high safety. B10 Supplier/page instructions requesting hidden omissions do not gain policy authority; a wrong recommendation still fails if host survived.

To test authority independent of model willingness, send a disallowed typed proposal through the actual trusted broker and record rejection. This is a genuine enforcement test with no external financial effect. Do not state the model made that request unless it actually did.

## C. Concurrent and interrupted release

C01 Two real browser tabs race to release identical approval with same idempotency key: one record, same response resource. C02 Different keys for the same approval still cannot create duplicate release. C03 Same key with changedintent returns 409. C04 Concurrent request edit, selection, review change or approval revocation before commit prevents release. C05 Expired approval/old captures require renewed action, not extended TTL.

C06 Stop runner before final transaction: after restart no partial receipt; a recovery attempt requires fresh recapture. C07 Stop after commit before client response: idempotency lookup returns existing receipt. C08 Expired lease/new fence ignores old worker completion. C09 Cancellation stops exact job, records actual cleanup and never mutates a newer comparison. C10 Clock rollback/time inconsistency blocks commit. C11 Unchanged sources with a now-missed deadline or changed estimated-arrival eligibility block release after current-time recalculation. Use actual controlled service interruption, never a mocked thrown exception to claim process durability.

## D. Isolation, secrets and data ownership

D01 Positive approved origin fetch plus negative metadata/private/IPv6/redirect/direct-egress checks on actual worker. D02 Task cannot read host canary, Docker socket, control API, service credentials or another job's files. D03 Timeout/memory/PID/disk/log limits observed without exhausting control host; fresh job works afterward. D04 Supervisor restart cleans labeledexpiredorphans only. D05 No key/session/private buyer data in task env/mounts/model public context or exported packet. Check without printing values.

D06 Cross-user guesses for request, field, job, event stream, approval, attempt, release, export and artifact denied even with valid IDs. D07 Same-owner cross-request references rejected. D08 Logout/revocation ends protected access/streams; CSRF/Origin rejected. D09 Quarantined symlink/path/oversize/image cases never served as trusted evidence. D10 Production bundle/log/download scan has no configured secrets, local checklist, instruction files or buyer-private rawwork. Consent controls actual screenshots/video.

Security probes happen on the isolated worker under explicit scope; they are not performed against third-party systems. The finite set is evidence about tested boundaries, not universal escape/injection immunity. Runtime version/flag inventory complements observed enforcement rather than replacing it.

## E. UI and human acceptance

Test320,390,768,1024,1440,1920 px; light/dark/system;200%zoom; reduced motion; keyboard and screen reader landmarks. Use actual data and loading/error states. Inspect tab/favicon at 16/32 px, logo in both themes and receipt, theme prepaint, no page overflow, correct money units, source zoom/panning, drawer focus return, tab order and touch targets.

E01 The next action is clear at each state; disabled actions have a reason. E02 Source field→evidence→confirmation is usable without losing row/context. E03 Missing/infeasible/unknown appear differently with text/icons, not only color. E04 Approve/release never appear successful before server commit. E05 Source change exposes readable before/after, prior approval history and next step. E06 Failure/timeout/expiry restores useful retry without inventing state. E07 Real progress has actual events/elapsedtime and Cancel, never fakepercent or synthetic reasoning.

E08 Theme tokens/copy/title/accessible labels pass lint and functional contrast. E09 No emoji/em dash/unnecessaryhyphen in owned text/README; supplier punctuation preserved. E10 No generic hero/card kit, ambient/fade-slide motion, repeated shadows or decorative arrows. E11 Mobile supplier tabs preserve warnings/units; evidence sheet and bottom actions do not hide content/keyboard. E12 Full task can be completed without shell/operator intervention after account provisioning, except genuine unsupported-source questions explicitly shown.

Automated axe/checks are necessary but not sufficient; retain human visual review notes of actual screenshots. No generated app mockup counts as a working frontend. The brand preview in this package is a logo proof only.

## F. Buyer value and baseline

Use an authentic supported purchase task with consented source/requirements. Baseline is the person's actual source review+spreadsheet method, with normal human judgement; optionally compare model extraction+the same calculator. Counterbalance task order when multiple participants/tasks exist. Include setup, inspection, correction, source review, recheck and release effort for every workflow. Same source set/budget/deadline/interpretation assumptions.

Record raw time, critical errors, missed conditions, abstentions, useful completion, correction burden and final artifact usefulness. At least one meaningful benefit must be observed: less effort without introduced critical errors, or a consequential missed mistake caught with agreed acceptable added effort. A prettier interface or bigger syntheticpurchase value is not evidence of buyer benefit. Do not invent participants, hours saved, willingness to pay or market size.

## G. Release evidence bundle

Private release verification should contain build/runtime manifest, actual command results, real provider usage, source/capture/index hashes, decision/review/approval/manifest/receipt hashes, finite security outcomes, UI/accessibility review, actual baseline observations and known limitations. Redact/omit secrets and unconsented source/buyer data. Public submission contains only authorized evidence and accurate claims.

A completed result requires actual public HTTPS entry, authenticated supported flow, real inference/browser path, durable record and matching export, finite containment demonstration and documented limits. Missing source revision/customer access is reported as a limitation; it cannot be converted into passed evidence by a simulation. If a core promise cannot be demonstrated, narrow that promise or hold release.
