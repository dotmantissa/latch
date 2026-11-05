# Private decision and internal release workflow

The API and workbench now support persisted comparisons, individual feasible-offer
selection, approval, all-source fresh recheck, immutable internal receipts and exports.
Public supplier inspection remains gated on actual source and buyer qualification.
The ordinary workspace starts empty. There is no sample purchase or checkout path.

A comparison is constructed by the server from the current request/policy and complete
latest successful inspection. It binds every source, capture, profile, extraction,
individual review revision/identity and image correspondence hash. The server derives
integer basket totals using the existing domain rules. Missing lines and unknown terms
retain null complete totals; zero is accepted only as a known value. Only complete,
reviewed, feasible offers with resolved image correspondence can be selected. Eligible
rank uses total, stated arrival and stable source ID; it does not make a selection.

Selection appends an immutable revision. Request/source/profile/review/selection changes
invalidate dependent state. Every command uses owner authorization, version preconditions
and explicit intent keys. Retrying the same selection, approval or release intent returns
its recorded result; changing its payload under the same key is rejected.

Approval binds the server comparison, selected supplier, named requester, session,
request version, policy and source evidence into canonical JSON and a schema hash.
It requires recent password verification and a scope acknowledgment, expires after ten
minutes and has append-only revocation. The dialog displays the saved quantities,
budget, deadline and total. No client or model supplies an approval packet or authority.

Release queues a 60 second all-source recheck, including rejected suppliers. It recaptures
identical approved page scope without repeating extraction or transferring human review
to new evidence. Different normalized text or sanitized raster hashes stop release and
revoke the old approval. The differences route retains both captures and bounded text
changes. New evidence requires another inspection and individual review; changed totals
are not invented from a diff. Unavailable, partial, expired or stale sources stop release.

The separate runner reconciles completed attempts after restart. Its short final database
transaction locks identity, request, attempt, job and profiles; validates the session,
current request/selection/reviews/approval, source set, fence, clock and capture freshness;
then creates one receipt and outcome together. A deferred database constraint checks
these invariants again during commit. Actual passage across the 60 second boundary was
rejected on Neon with no surviving receipt. Uniqueness permits one receipt per request
version; a lost response is recovered through the original attempt or authorized receipt
lookup. Cancellation can stop an attempt even after recapture completes, until the
internal receipt commits. No network request or PDF rendering occurs in that transaction.

Receipts retain the approved worksheet, reviewed source packet, selected supplier,
approval identity/hash, fresh source manifest and observed timestamps. They describe an
internal decision only: no supplier order, payment, stock reservation or price lock.
JSON, offline PDF and ZIP downloads require the owner session. Deterministic export bytes
and their SHA256 hashes are persisted separately, so renderer failure cannot repeat a
release. ZIP contains receipt JSON/PDF, approved/fresh sanitized PNGs and exact text,
source index, byte manifest and a scope note. It excludes model transcripts and runtime
credentials/paths. PDF rendering loads fixed fonts/codecs, then denies file/network/child
process authority through the same syscall allowlist as the PNG sanitizer.

Key routes:

- `GET /requests/{id}/decision`, `POST /requests/{id}/comparisons`.
- `POST /requests/{id}/selections`, `POST /requests/{id}/approvals`.
- `POST /approvals/{id}/revoke`.
- `GET|POST /requests/{id}/release-attempts`, `GET /release-attempts/{id}`.
- `POST /release-attempts/{id}/cancel`.
- `GET /releases/{id}`, `GET /releases/{id}/exports/{json|pdf|zip}`.
- `GET /captures/{id}` for authorized historical successful captures.

Paths above are under `/api/v1`. The UI links saved worksheets to evidence and comparison,
shows actual release status, and preserves earlier approval and receipt history.

Real Neon authority assertions cover revocation, session/profile/review/request/selection
changes, stale or changed evidence, commit expiry, cancellation and duplicate release.
Populated encrypted restore and authorized byte-identical exports passed. These isolated
security assertions are not supplier-world recapture or observed buyer approval. A genuine
source change, a complete qualified buyer task, human effort/value and public deployment
remain unverified. See [recovery](RECOVERY.md) and [correspondence](CORRESPONDENCE.md).

The [current workflow record](evidence/WORKFLOW_STATUS.json) lists separate local,
real Neon, genuine supplier and browser checks. Earlier evidence files retain their
original milestone scope and point to this record for current software status.
