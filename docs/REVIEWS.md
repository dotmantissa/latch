# Individual captured-term review

The review API records one authenticated requester decision at a time. It preserves
the immutable extraction and captured source text, then appends a confirm, correct or
dispute record with reviewer identity, time, reason and exact evidence spans. It offers
no bulk confirmation command. The model receives neither these commands nor session
credentials and cannot create a review, approval or release.

Confirmation accepts only a supported original value and its exact original quotes.
Unknown and ambiguous values cannot be confirmed. Correction requires a strict value
type, a reason and unique quotes from that same capture. Money must match a literal
captured dollar amount. A requester may explicitly resolve competing price bases with
a reason; automatic extraction retains its conservative ambiguity check. Disputing a
field removes its usable value while retaining the original proposal and earlier review.
Unknown shipping cannot become zero merely because a page mentions free shipping.

Each mutation requires CSRF/Origin, `If-Match`, request version, original proposal hash,
expected review revision, an idempotency key and an explicit acknowledgment that the
requester viewed the field evidence. The acknowledgment is an attribution, not proof
that a human read the source or that its claims are true. Records reference only the
captured source; unrelated additional facts cannot silently fill missing terms.

The current request and latest successful source packet must still match. Archived or
changed requests, replaced captures, expired/inactive profiles and inspections in
progress block new review. Concurrent tabs serialize on a revision check: one decision
persists and the stale decision fails. An identical retry returns its existing record;
the same key with changed intent fails. Each extraction is limited to 1000 review rows.

Migration 004 adds an atomic revision pointer and immutable review rows. Existing
migrations stay unchanged. The API exposes the original field, latest attributed
decision, checked count and a paginated history. Derived basket calculation uses the
existing integer rules. A line is reviewed only after every required item field is
checked; source terms require their own complete checks. Missing or disputed terms
remain null and block feasibility. This implementation does not create an approval,
selection, order or release.

Available routes:

- `GET /api/v1/extractions/{id}/review` returns source review state, revision ETag and
  any derived basket using saved buyer constraints.
- `GET /api/v1/extractions/{id}/reviews?before=N&limit=25` returns immutable history,
  newest first, with at most 50 rows per page.
- `POST /api/v1/extractions/{id}/reviews` appends one decision and returns its identity
  and revision. The first mutation uses `If-Match: "0"`.

Other owners receive 404, stale preconditions receive 412 and invalid evidence/type
receives 422. The captured evidence API includes its extraction ID for these routes.
Historical review remains readable after a request changes, without permitting new
decisions against that old packet.

The [protocol evidence](evidence/REVIEW_STATUS.json) uses a real worker supplier capture,
actual Vultr extraction, Neon and authenticated HTTP. Automated assertions corrected
the captured surcharge amount, disputed it, retained original ambiguity and history,
and tested competing revisions, ownership and stale requests. They are command-boundary
checks, not observed human buyer review or complete purchasing acceptance. The isolated
schema and all assertion rows are removed afterward.

```sh
.venv/bin/python -m scripts.check_evidence --review-commands
```

The source review interface is available at `/requests/{id}/evidence`, linked from a
saved worksheet. It loads protected captures and review state, with explicit empty,
missing extraction, unavailable and historical states. Supplier image correspondence,
full runner comparison integration and actual human evaluation remain pending. Public
supplier inspection is still gated; no application buyer request or release was seeded.

Selecting one field opens its exact captured text with supporting spans highlighted,
original extraction, latest attributed decision and an optional screenshot. Highlight
positions count Unicode code points to match server offsets. Screenshots preserve their
original colors and offer fit, actual size and double size. External source links open
separately; they are never substituted for the immutable capture.

Each field has Check this term, Correct value and Mark unclear actions. Unsupported
original values cannot be checked. Corrections require a strict USD/whole number/boolean/
coverage/timezone value as appropriate, exact unique captured quotes and a reason.
Both correction and dispute require reasons. Every decision requires explicit evidence
acknowledgment; there is no bulk confirmation. Original proposals remain visible and
review history is paginated. Review counts and totals come from refreshed server state.
Missing totals remain Not confirmed.

The review view now reports `review_allowed` and `review_blocker` alongside `current`.
Changed packets, active inspections and inactive/expired supplier profiles disable new
decisions in the interface. This read status is advisory; existing transactional command
checks still enforce eligibility. A conflict freezes submission until an explicit reload
and renewed evidence acknowledgment. Identical transport retries reuse their command key.

On wide screens evidence sits beside the ledger. At smaller widths a native modal sheet
traps keyboard focus, closes with Escape and restores the chosen field. Source references
and history retain readable text in both themes; screenshots load only after a request.

The [interface evidence](evidence/WORKBENCH_STATUS.json) records actual browser checks on
fresh real supplier evidence in an isolated Neon schema. Individual correction/dispute/
check, exact quote and acknowledgment rejection, reload persistence, stale tabs, original
history, inactive profiles and active inspections were observed. Both themes passed six
widths, four axe cases, keyboard focus/Escape and 200% zoom/reduced motion. Actual screenshots
were inspected. These automated decisions are not observed human buyer acceptance.
The expiry time is immutable; an attempted edit was correctly denied. Its actual passage
was not observed. Verification schemas, worker tasks and local HTTPS processes were cleaned.

```sh
LD_LIBRARY_PATH="$PWD/.tools/browser-libs/usr/lib/x86_64-linux-gnu" \
  PLAYWRIGHT_BROWSERS_PATH=.tools/browsers \
  .venv/bin/python -m scripts.check_evidence --browser-review
PATH="$PWD/.tools/node/node_modules/node/bin:$PATH" node scripts/check_review_values.mjs
```

The private `var/review-browser/phases.json` checkpoint is scoped to the random verification
schema. Optional `--browser-retry` keeps that isolated fixture for at most ten minutes after
a failed assertion, so local repairs can resume without repeating source/model calls or
rewriting immutable reviews. A fresh invocation uses a new schema and repeats the checks.
