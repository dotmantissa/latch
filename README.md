# Latch

Check the terms. Keep the decision yours.

Latch helps a requester put an equipment purchase on paper: required items, quantities,
budget, deadline and supported supplier pages. The local workspace now saves drafts and
revisions in Neon Postgres, with named accounts, private sessions and a readable history.

The interface uses warm limestone, oxblood, the original Latch mark, and light and dark
appearance. Its request rail and wide worksheet keep the details easy to return to.

Supplier inspection, model extraction, evidence review, approval and source recheck will
connect to Vultr when access is available. Those actions remain unavailable in this build.
A future release will create an internal purchase record without placing a supplier order.

Start with [local setup](docs/LOCAL.md). The connection is kept in an ignored private file.
Create your account through the terminal command, then run bash scripts/dev.sh to open
https://localhost:8443. No supplier pages or requests are seeded.

| Document | What it covers |
| --- | --- |
| [Local workspace](docs/LOCAL.md) | Run the app, provision an account and verify real Neon persistence |
| [Architecture](ARCHITECTURE.md) | Product scope, boundaries and future review and release rules |
| [Implementation roadmap](docs/IMPLEMENTATION.md) | Available packages and remaining live gates |
| [Data and API contracts](docs/CONTRACTS.md) | Versioned records, ownership, API and worker contracts |
| [Design specification](docs/DESIGN.md) | Layout, typography, themes and accessible interactions |
| [Security and operations](docs/SECURITY.md) | Sessions, isolation, deployment and recovery requirements |
| [Runtime probes](docs/P0.md) | Deferred source and Vultr capability checks |
| [Acceptance plan](docs/ACCEPTANCE.md) | Future real supplier journeys and buyer evaluation |
| [Brand assets](assets/brand/README.md) | Logo masters, fonts and browser icons |
| [Sources](docs/SOURCES.md) | Official technical references |

The automated checks cover deterministic arithmetic, real HTTP identity, owner isolation,
Neon migrations and saved revision recovery. Live supplier accuracy, Vultr inference,
worker containment, purchase release and buyer value still need their own evidence.

Earlier research remains in [the archive](research/README.md). Its synthetic examples are
historical planning material. The local recovery checklist stays private and ignored.
