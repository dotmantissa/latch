# Official sources and unresolved checks

Sources consulted November 3, 2026. The architecture is our design; the links support the underlying platform behavior, not a guarantee that our implementation works. Runtime versions, pricing, source admission and user eligibility must be verified again when implementation starts.

| Source | What it informs |
| --- | --- |
| [Vultr event playbook](https://lablab.ai/ai-hackathons/vultr-hackathon) | Chosen execution pattern, Vultr services and deliverables |
| [Vultr inference overview](https://api.vultrinference.com/docs) | Configured server endpoint and provider capability discovery |
| [Vultr chat completion reference](https://api.vultrinference.com/docs/reference/create-chat-completion) | Future structured/tool/image request implementation; actual model support still needs a live call |
| [React](https://react.dev/learn) | Component/state foundation |
| [Vite](https://vite.dev/guide/) | Frontend build and supported runtime prerequisites |
| [Node release schedule](https://nodejs.org/en/about/previous-releases) | Supported LTS rather than the existing shell's Node 20 |
| [Python 3.13](https://docs.python.org/3.13/) | Explicit backend runtime family |
| [FastAPI deployment](https://fastapi.tiangolo.com/deployment/) | API service/process deployment considerations |
| [Neon pooling](https://neon.com/docs/connect/connection-pooling) | Transaction pool behavior, direct migration connection and transaction local settings; reviewed November 4, 2026 |
| [Psycopg 3](https://www.psycopg.org/psycopg3/) | Pinned Python Postgres driver and explicit transaction boundaries |
| [SQLite WAL](https://www.sqlite.org/wal.html) | Single-host WAL behavior, contention and the documented March2026 WAL reset fix |
| [Playwright Python containers](https://playwright.dev/python/docs/docker) | Browser/package version alignment and root/untrusted-page warnings |
| [gVisor Docker setup](https://gvisor.dev/docs/user_guide/quick_start/docker/) | Runtime installation/compatibility spike |
| [gVisor security](https://gvisor.dev/docs/architecture_guide/security/) | Isolation limits and need for external network/resource controls |
| [Docker resource controls](https://docs.docker.com/engine/containers/resource_constraints/) | Explicit cgroup/CPU/memory controls |
| [Docker security](https://docs.docker.com/engine/security/) | Runtime administration and container boundary risks |
| [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) | Cookie/session lifecycle and server enforcement |
| [OWASP SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) | Source URL/network policy and redirect/private-address defenses |
| [Caddy HTTPS](https://caddyserver.com/docs/automatic-https) | Public DNS, ports, certificate storage and TLS setup |
| [WCAG contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) | Text contrast targets; UI needs live accessibility review too |
| [Lucide React](https://lucide.dev/guide/react) | Real icon library and accessible SVG components |
| [Manrope](https://fonts.google.com/specimen/Manrope), [DM Serif Display](https://fonts.google.com/specimen/DM+Serif+Display) | Chosen typography; actual font files/licenses/hashes are preserved in assets |

Open gates: real supported buyer/source fit, Vultr account/credits/remote prize eligibility, actual supported model tool/image behavior, hardened browser compatibility, observed latency/cost, source revision availability, genuine baseline task and final submission form requirements. No fabricated value is inserted for any missing gate.
