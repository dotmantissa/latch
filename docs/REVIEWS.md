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

The source review workbench, supplier image correspondence, full runner comparison
integration and actual human evaluation remain pending. Public supplier inspection is
still gated; no application buyer request or successful release was seeded.
