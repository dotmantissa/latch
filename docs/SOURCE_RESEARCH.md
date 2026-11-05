# Supplier compatibility investigation

Observed 2026-11-05. This is passive public page research for implementation, with no
real buyer acceptance task or admitted application profile yet.

The actual [Ubiquiti U6+ product page](https://store.ui.com/us/en/products/u6-plus)
returned HTTP 200 with HTML and one main region. Its visible server-rendered content
names the product, description, quantity control, Add to Cart and accessories. It displays
both $129.00 and $142.00 Surcharge incl. That difference needs an explicit price basis;
the lower amount cannot become the authoritative comparison price automatically.

The visible content did not establish all essential terms for the planned equipment
basket: exact coverage for three requested items, availability for required quantities,
tax/shipping and an interpretable latest arrival. Accessory suggestions are separate
products and do not establish a complete bundle quote. A reviewed profile must retain
the relevant offer and terms regions and represent these missing or disputed values.

The store's robots path redirected to a 404 page. That observation establishes no capture
permission. The independently attempted CDW product page and robots endpoint failed to
connect from the development environment. No access control was bypassed.

The isolated worker subsequently captured that exact public product page with HTTP 200,
a 1440 by 1699 raster and 910 characters of relevant text, then confirmed container
cleanup. The raster was visually inspected. Some product images were blocked by the
strict asset policy. The offer region retained both prices; it did not establish complete
shipping, tax, stock, arrival or purchase terms. The worker-only research profile and
explicit static asset origins expire on November 7. No application source profile,
account or buyer request was created.

Actual Vultr extraction required two calls: the first proposal was rejected because its
repeated price quotes did not identify unique text spans. One repair produced valid
exact surrounding quotes. Independent checks reproduced the capture and proposal hashes
and every span. Price remains ambiguous with a null value; all missing material terms
remain unknown and all human review flags remain false. This establishes bounded
source-text extraction, not completed supplier qualification or buyer acceptance.

See [EXTRACTION.md](EXTRACTION.md) for the implementation and its limits. Continue
supplier access and completeness investigation using an actual purchase requirement.
Artifact sanitization, persisted evidence review and supplier image correspondence
validation remain separate finish gates.
