# Provisional source extraction

The control-side extraction client independently validates bounded capture bytes,
exact page URLs, screenshot dimensions, content hashes and capture intervals before
sending public source text to Vultr. Inference receives only public item specifications,
required quantities and captured page text. Private specifications, buyer budget,
delivery notes, cookies and infrastructure credentials are excluded.

`ProposedTerms` requires every item and material term, distinguishes supported,
ambiguous and unknown values, and preserves null separately from zero. Unknown fields
include a reason; ambiguity requires conflicting exact captured quotes. Supported
values require unique text spans. Money must match literal captured dollar amounts;
nearby competing prices block a supported price. This validates attribution and shape,
not semantic truth, quantity basis, completeness or supplier honesty.

The provider receives strict JSON instructions and no tools. Duplicate keys, nonfinite
JSON, unexpected authority fields and foreign item keys are rejected. Extraction has
at most three calls, including two bounded format or grounding repairs, and a fixed
4096 output token profile. The existing capability profile remains 1024 tokens.
Validated proposals retain model, prompt and schema versions, a capture hash, exact
text offsets and a canonical proposal hash. Conversion into domain offers always
sets human review false. The model cannot approve, mark feasibility or create release.

The durable runner now loads only the public specification, stable item key and
required quantity from the pinned request version. It stores the sanitized capture,
runs extraction outside the transaction, and stores the validated proposal under the
same job, fence and capture identity. Fixed phase events record extraction start and
storage without including source text, provider output or private notes.

Each source extraction has one absolute 60 second deadline shared by all repairs,
bounded by the original 180 second job deadline. During waiting headers or response
streaming, five second polling rechecks the job fence, cancellation,
request version and profile, and renew the lease. Deadline or cancellation closes the
in-flight HTTP request. Provider errors and invalid usage fail closed. A response
truncated by the output limit can request one of the same two formatting repairs;
it can never become an accepted proposal. No retry extends the source or job budget.

Successful job completion requires every current source to have a cleaned capture
and a valid immutable extraction from the current fence. Publication revalidates exact
spans, typed values, item keys, proposal hashes, bounded usage and active profiles.
An abandoned or incomplete attempt cannot publish evidence. Unknown terms can be
valid proposals; a completed extraction does not imply a complete or feasible offer.

The real public Ubiquiti investigation is recorded in [SOURCE_RESEARCH.md](SOURCE_RESEARCH.md)
and [extraction scope](evidence/EXTRACTION_STATUS.json). Its competing prices and absent
material terms remain unresolved. Private source bytes, model proposals, validation
diagnostics and usage are in ignored operator evidence, not public deliverables.

To repeat that explicitly scoped research while its worker profile is active:

```sh
.venv/bin/python -m scripts.check_supplier_extraction --capture-only
.venv/bin/python -m scripts.check_supplier_extraction --extract-existing
```

The command uses the established private supervisor tunnel and owned ignored inference
credential. It creates no application buyer data. Source-text extraction and
[sanitized evidence storage and delivery](EVIDENCE.md) are implemented, alongside
[individual review records and their interface](REVIEWS.md). Supplier vision
[correspondence](CORRESPONDENCE.md) and the [comparison workflow](WORKFLOW.md) are
implemented; observed human and qualified supplier acceptance remain pending.
Public inspection remains gated.

The [durable runner check](evidence/RUNNER_EXTRACTION_STATUS.json) used a fresh actual
supplier capture, three Vultr calls and isolated Neon storage. It completed with an
ambiguous null price and no human review. Its earlier failed attempts published no
packet; the provider and publication fixes retained the original limits.

To repeat the actual runner boundary check while the worker profile is active:

```sh
.venv/bin/python -m scripts.check_runner_extraction
```

The helper creates only labeled source-research rows in a generated isolated schema,
revokes its worker fence and drops that exact schema after checking the result. Its
recovery note and bounded diagnostics remain under ignored var/runner-extraction-check.
