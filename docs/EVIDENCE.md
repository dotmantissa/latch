# Sanitized captured evidence

The runner independently revalidates the worker's bounded capture before admitting
evidence. Every screenshot is decoded and re-encoded as a fresh RGB PNG in a separate
Linux process. Its fixed seccomp policy denies file opening, sockets, child processes,
execution and filesystem changes before any image bytes are read. The child receives
only standard descriptors and no inherited environment or credentials. Missing
libseccomp, decode errors and resource-limit failures reject the artifact.

The decoder uses pinned Pillow 13.0.0, checks PNG CRCs, limits input and output to
10 MiB, dimensions to 4000 by 16000 and total pixels to 12 million. Memory is limited
to 384 MiB, CPU to six seconds and elapsed time to ten seconds. Animation, unsupported
color modes and transparency are rejected. Fresh raster allocation discards comments,
EXIF, color profiles and other supplier metadata. The API performs bounded byte/header
checks; it never invokes an image decoder.

Sanitized files live in an owned mode 0700 directory, default `var/evidence`, selected
by `LATCH_EVIDENCE_DIR`. Files have mode 0600 and names derived only from SHA-256.
Writes are fsynced and admitted atomically without overwriting existing content.
Admission requires Linux `renameat2` with `RENAME_NOREPLACE`, avoiding an intermediate
hardlink or partial target if the runner stops during a write.
Reads reject symlinks, hardlinks, special files, public permissions, size disagreement
and changed hashes. Raw worker bytes remain separately quarantined and have no product
download route. Interrupted persistence can leave private orphan files; retention and
encrypted backup/restore are still pending and files must not be deleted blindly.

Migration 003 adds immutable captures, page metadata/text and provisional extractions.
It preserves migrations 001 and 002. Composite foreign keys bind each capture to its
owner, request version, exact source, task and job fence. A write requires a current
lease, unchanged request, confirmed cleanup, matching capture hash and active profile.
Extraction storage reproduces the typed values, exact spans and proposal hash from
the saved text; arbitrary field kinds, duplicate fields and modified evidence fail.
Provider usage is stored privately and excluded from API responses.

The application was verified empty immediately before applying 003. The real Neon
regression checks also upgraded a populated isolated version-1 schema and preserved
its account record. This is migration evidence; it does not establish backup/restore.

The deterministic `visible-text-v1` fingerprint includes all retained offer/terms text,
page URLs and the exact source profile. It normalizes Unicode NFC, line endings and
documented whitespace only. New exclusions or unknown content change the fingerprint;
model summaries and screenshot byte equality do not decide source freshness.

Authenticated routes:

- `GET /api/v1/requests/{id}/evidence?version=N` returns the latest successful inspection
  for that owner and saved request version, with source text, sanitized artifact IDs,
  capture intervals and any provisional extraction. Its state is explicitly unreviewed.
- `GET /api/v1/artifacts/{id}` returns only the authorized re-encoded PNG. It sets PNG
  content type, nosniff, no-store and same-origin resource policy. Unknown or other-owner
  IDs return 404; missing/corrupted files return a safe unavailable error.

Captures from running, failed or abandoned job fences cannot publish files. These
routes provide evidence infrastructure; [individual review commands](REVIEWS.md) are
implemented with the individual source review interface. Public supplier inspection
remains gated. Successful capture means collected evidence,
not complete purchasing terms, buyer review, approval or release.

The actual source-only check creates an isolated Neon schema, captures the real public
Ubiquiti page on the established worker, calls Vultr, sanitizes/stores evidence and
checks protected HTTP delivery. It has no buyer budget, consent or purchase acceptance.
The schema is dropped afterward; private recovery IDs and results are in
`var/evidence-check`. Repeat while the worker research profile is active:

```sh
.venv/bin/python -m scripts.check_evidence
```

Actual runner interruption and fresh-fence recovery also verify durable sanitized
technical-documentation evidence:

```sh
.venv/bin/python -m scripts.check_runner
```

See [public evidence scope](evidence/EVIDENCE_STATUS.json) and
[supplier research](SOURCE_RESEARCH.md). Actual human review, supplier image
correspondence, buyer fit, complete terms and release acceptance remain pending.
