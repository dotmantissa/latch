# Captured image correspondence

Every new inspection must store one immutable raster correspondence result per source
before its current fence can publish. The result binds the source ID, capture hash,
ordered sanitized PNG hashes, page indices, public item keys, model and schema version.
Exact unique captured lines are supplied as indexed quote options. The trusted adapter
resolves those indices into literal quotes and validates pixel regions against the raster.
An invented quote, duplicate observation, wrong page/hash/key, invalid region, tool call,
truncated answer or extra authority field fails closed.

The runner makes one image call per source, with no repair loop, a 45 second shared call
budget, 4096 output tokens and 20 KiB retained answer limit. Text extraction retains its
three call/60 second budget. Three sources therefore permit at most twelve inference
calls under the original 180 second inspection deadline. Lease renewal, cancellation,
profile/version activity and final complete-set validation continue through inference.
Only public item specifications and sanitized public source evidence enter the model.

Product image review is an explicit operator profile capability, defaulting to false.
It does not widen asset/network permission. Until qualified product images are available,
trusted code emits item abstention and rejects model item conclusions. A qualified
capability needs a new immutable profile version. Agreement remains a provisional
observation; it never checks a term, selects an offer or approves a release. Missing
correspondence, abstention and disagreement block selection.

Actual Ubiquiti research capture, Vultr inference, Neon persistence and current-fence
publication passed. Product photographs remain blocked by the existing asset policy;
item correspondence abstains and the competing prices remain ambiguous. An earlier
provider diagnostic invented quotes and treated a title as visual proof; exact quote
indices and the operator capability gate now reject that behavior. No buyer acceptance
or complete supplier quote is inferred from these checks.

Run the retained public-source diagnostic or a fresh isolated runner check:

```bash
PYTHONPATH=. .venv/bin/python scripts/check_correspondence.py
PYTHONPATH=. .venv/bin/python scripts/check_runner_extraction.py
```

Both use owned ignored credentials and private research artifacts. Neither populates
application buyer data nor enables public supplier inspection.

The [current correspondence record](evidence/CORRESPONDENCE_STATUS.json) retains the
adverse provider observations and the scope of the successful actual-source runner check.
