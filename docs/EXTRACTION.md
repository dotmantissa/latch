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
[sanitized evidence storage and delivery](EVIDENCE.md) are implemented. Durable reviewed
fields, supplier vision correspondence and the review workbench remain pending.
Public inspection remains gated.
