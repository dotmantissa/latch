# Latch

Check the terms. Keep the decision yours.

Inspect public supplier offers in a contained browser, verify captured evidence with Vultr inference, and keep the final decision with the requester.

[Open the public app](https://latch.64.177.55.57.sslip.io) and choose **Try a private demo**, then **Start the U6+ source demonstration**. Check the public item description and consent disclosure before starting an inspection. Each visitor has a separate workspace and two live inspections. Demo sessions can review evidence and compare terms; approval requires a named account and recent password verification.

The demonstration visits the real Ubiquiti U6+ product page. Its USD 200 budget and deadline seven days away are labelled demonstration requirements. Missing shipping, tax, arrival and purchase terms stay unknown. Product photographs outside the reviewed capability produce image abstention. An incomplete quote cannot become a feasible selection or an approved purchase. No buyer acceptance or supplier order is claimed.

## How Vultr powers Latch

Vultr Cloud Compute hosts the public React application, FastAPI backend and separate durable runner on an Ubuntu control VM in Atlanta. Caddy provides HTTPS. A second Vultr VM runs the browser task supervisor and disposable gVisor containers. Vultr is the system that plans and executes inspections, with Neon Postgres holding durable records.

All model calls use Vultr Serverless Inference. The exact configured model identifier is recorded in the deployment guide and checked against the authenticated provider catalog. The agent receives only public item descriptions and admitted source IDs/URLs. Its validated plan orders exactly those sources. Playwright captures approved public pages; bounded extraction and screenshot correspondence produce provisional evidence for individual review. Private specifications, budget, delivery notes and identity do not enter inference requests.

The worker has no model, database or deployment credentials. It accepts fixed commands over a restricted SSH tunnel and mutual TLS. Browser tasks run without root, with Chromium sandboxing, gVisor, seccomp, resource limits, an exact public URL proxy and host firewall restrictions. A separate sweeper can remove a task when its executor stops. The control host stores evidence on an encrypted LUKS2 volume; separate API and runner accounts share only the explicit artifact group.

## Decisions stay reviewable

Requests have immutable saved versions. Individual reviews preserve source attribution and exact quoted spans. Comparisons use integer arithmetic and keep unknown totals unresolved. Only feasible offers can be selected. Approval binds the exact reviewed packet, expires and can be revoked. Release recaptures every source and commits an immutable internal receipt only after freshness, ownership, eligibility and approval checks pass at database commit. It does not place an order.

Authorized JSON, PDF and ZIP exports and encrypted consistent backups are implemented. Restores use a new isolated schema and revoke restored sessions. The public source remains unsuitable for a complete release because its quote evidence is incomplete.

## Verification and submission

The [deployment guide](docs/DEPLOYMENT.md) covers host setup, service isolation, source admission and recovery. The [submission package](docs/submission/ENTRY.md) contains the entry description, slides, cover and recorded demonstration. Watch the [recorded demonstration](https://latch.64.177.55.57.sslip.io/assets/submission/demo.mp4) or open the [slides](docs/submission/slides.pdf). The [recording notes](docs/submission/DEMO.md) distinguish actual automation and containment observations from human buyer acceptance.

Automated checks cover arithmetic, real HTTP ownership and sessions, isolated Neon migrations, queue admission and replay, lease recovery, review history, commit guards and encrypted restore. Actual Vultr worker checks exercise metadata/private/loopback network denial, direct socket denial, watchdog termination and cleanup. [Current deployment evidence](docs/evidence/DEPLOYMENT_STATUS.json) records the finite checks and their date.

## Run and understand the project

Start with [local setup](docs/LOCAL.md). Use owned private files for the database connection and keys; no credential belongs in a frontend variable, shell argument or commit. Public inspection is enabled only through explicit operator configuration and fresh matching worker profiles.

| Document | What it covers |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | Product and trust boundaries |
| [Deployment](docs/DEPLOYMENT.md) | Vultr hosts, HTTPS, services and recovery |
| [Contracts](docs/CONTRACTS.md) | Versioned data, API and task commands |
| [Evidence](docs/EVIDENCE.md) | Captures, isolation, hashes and delivery |
| [Reviews](docs/REVIEWS.md) | Individual field decisions and history |
| [Correspondence](docs/CORRESPONDENCE.md) | Vision attribution and abstention |
| [Workflow](docs/WORKFLOW.md) | Comparison, approval, recheck and internal receipts |
| [Recovery](docs/RECOVERY.md) | Encrypted backup and isolated restore |
| [Brand](assets/brand/README.md) | Original logo and licensed fonts |

Original project code is [MIT licensed](LICENSE). Bundled fonts retain their SIL Open Font License notices. Earlier research remains in [the archive](research/README.md); historical scenarios are planning material.
