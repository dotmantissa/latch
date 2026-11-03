# Latch

Check the terms. Keep the decision yours.

Latch is being designed for people who need a complete equipment order, not a promising subtotal. It brings supplier offers and their supporting terms into one place, so the requester can see what is included, check the important details and approve a specific version.

Before a purchase request is released, Latch checks those sources again. Changed or unavailable terms keep the request on hold. A release creates an internal purchase record. It does not place a supplier order, reserve stock or guarantee a price.

This repository contains the architecture, brand assets and initial runtime scaffolding. Application work follows the live feasibility prerequisites. No customer results, live integrations or security outcomes are claimed here.

Start with [the architecture](ARCHITECTURE.md). Follow [the implementation roadmap](docs/IMPLEMENTATION.md) and [the runtime setup](docs/P0.md).

| Document | What it covers |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | Product scope, system boundaries, features, calculations, approvals and release |
| [Implementation roadmap](docs/IMPLEMENTATION.md) | Work packages, dependencies and evidence needed to finish each step |
| [Data and API contracts](docs/CONTRACTS.md) | Records, ownership, versioning, endpoints, worker messages and exports |
| [Design specification](docs/DESIGN.md) | Layout, typography, colors, themes, motion, accessibility and user flows |
| [Security and operations](docs/SECURITY.md) | Credentials, isolation, deployment, backups and recovery |
| [Acceptance plan](docs/ACCEPTANCE.md) | Actual service journeys, failure cases, usability checks and evidence |
| [Brand assets](assets/brand/README.md) | Logo masters, wordmarks and browser icons |
| [Sources](docs/SOURCES.md) | Official technical references used for this plan |

The visual direction uses oxblood, warm limestone and a wide document workspace. Manrope keeps the controls clear. DM Serif Display gives request names and important totals a quieter editorial character. A small latch seam marks the point where reviewed evidence meets release.

The interface will include light and dark themes, proper icons, visible keyboard focus and motion that responds to a person's actions. Warnings about money and approval will stay precise. A little warmth is welcome elsewhere. Nobody needs extra paperwork. The record should make the decision easier to explain.

All agent calls are planned for Vultr Serverless Inference. Browser work will run in disposable isolated environments on Vultr. There is no blockchain component in this scope.

Earlier research is preserved in [the research archive](research/README.md). Its synthetic examples and retired product name are historical material, not a live demonstration or the current build specification.

The architecture and brand form the implementation baseline. The local recovery checklist remains private and ignored.
