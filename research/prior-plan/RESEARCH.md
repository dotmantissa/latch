# Vultr Agent Rush: research and product decision

Research refreshed November 3, 2026. Planning artifact; no product has been implemented or benchmarked. This resumes session `01a1a143-f0ef-74c2-adef-885a901917a3`.

**Current direction:** [PRODUCT_REVISION.md](PRODUCT_REVISION.md) and the rewritten [BUILD_PLAN.md](BUILD_PLAN.md) supersede the original recommendation below. QuoteProof v2 reviews a three-item IT deployment basket, gathers source evidence through Pattern B, uses trusted deterministic purchase rules and rechecks all decision sources before internal release. Generated Python and the redundant validator are removed. A changed supplier source invalidates approval; an unavailable source blocks release. Buyer/source fit, real benefit, competitive advantage and runtime enforcement remain untested.

**Historical scrutiny:** [JUDGE_REVIEW.md](JUDGE_REVIEW.md) remains the independent assessment of v1. Its evidence gates are still open. The numerical candidate scores below are historical, withdrawn planning estimates and must not be used as ratings or win probabilities. The older recommendation and dual-pattern architecture are retained here only as research history.

## Historical v1 recommendation — superseded

Build **QuoteProof** (working name): a procurement agent that turns a purchase request and three supplier pages into a feasible buying recommendation, with screenshots, executed calculations and a reviewable order draft. Demonstrate that a hostile supplier page cannot authorize an action, and that failed code execution is confined to a disposable sandbox.

Enter **Blast Radius Zero**, combining code execution and browser use in one workflow. Borrow the enterprise usefulness of the Future of Work direction; do not assume entering both challenges is permitted. The differentiator is the evidence and execution boundary around a consequential decision. Quote comparison alone is already a competitive category.

This is a strategy to improve our chances, not a predicted win probability. The available records establish winners and their reported designs; they do not reveal private judge deliberations or prove causation.

## Event facts and unresolved details

The user's supplied brief establishes the required Vultr VM control plane, Vultr Serverless Inference for every agent model call, isolated execution on Vultr, public repository, public application, architecture explanation and a recorded containment moment. Four criteria are named: technology, presentation, business value and originality. No criterion weights were supplied.

The organizer's fuller playbook describes two challenge choices. Blast Radius Zero allows either or both execution patterns. Future of Work includes procurement among its business areas. Both require Vultr deployment; the inference and sandbox requirements specifically apply to Challenge 1. These are challenge choices, not evidence of separate prize pools or permission to combine entries. [Organizer playbook](https://lablab.build/ai-hackathons/vultr-hackathon)

The live dashboard currently lists kickoff **November 3, 16:00 UTC** and submission close **November 8, 23:00 UTC**. Lagos is UTC+1: **17:00 November 3** and **00:00 November 9** respectively. This supersedes the previous session's 15:00/22:00 UTC notes. Set our internal deadline to **November 8, 18:00 UTC / 19:00 Lagos** and reconfirm the actual form before submission. [Live dashboard](https://lablab.ai/ai-hackathons/vultr-hackathon/live)

The supplied prize breakdown is $5,000 cash + $3,000 credits for first, $3,000 + $1,000 for second, and $1,000 + $1,000 for third. Teams may have 1–6 members. Registration on LabLab and participation in its Discord are required. These are supplied event facts, also reflected on the [Vultr event page](https://community.vultr.com/e/vultr-agent-rush-hackathon).

The organizer page adds a slide presentation, public README explanation of Vultr infrastructure, original/MIT-compliant submissions, and LabLab as the judging submission destination. Vultr Community sharing is optional. Credit instructions mention an email not previously associated with a Vultr account; do not assume an existing account qualifies. [Event requirements](https://lablab.build/ai-hackathons/vultr-hackathon)

The general rule book defaults to MP4/MOV video and PDF slides but says event-specific forms take precedence. It does not establish a hard video duration for this event. [Rule book](https://lablab.ai/hackathon-rules)

Ask organizers, without delaying planning:

1. Can a fully remote team win the same first prize, and is a live finalist presentation required?
2. Are the two challenges judged together? Can one project select only Blast Radius Zero while demonstrating procurement value?
3. What is the final deadline and video limit in the submission form?
4. Do the credits cover inference, and what are the promotion's account and expiry conditions?
5. What existing infrastructure may be reused, and how should it be disclosed?

No organizer message has been sent. On-site attendance and team capacity are unknown; the plan assumes one engineer working remotely on a fresh build.

## Eight winner cases across five comparable events

Comparison priority: the same organizer and sponsor first; then similar sandbox/browser execution; then similar agentic research products. Severity below is an analytical judgment about the task in that event, not an independently measured customer loss. Project descriptions are builder claims unless explicitly attributed to the organizer. Repositories were read, not executed or audited.

| Project and verified result | Pain point and relative severity | Reported implementation | Transfer to our entry |
| --- | --- | --- | --- |
| **Deals Machine** — first in Vultr and Speechmatics prize categories, AI Agent Olympics 2026 | Follow-up and CRM work consume attention in small revenue teams. High business relevance; closest sponsor precedent. | Call audio becomes lead memory, planned follow-ups, drafts and activity updates; builder describes a Vultr worker and defenses against malicious inbound content. | Choose a named business operator; complete an operational chain; make Vultr central. |
| **ContextGuard** — second in Vultr category, same event | Decisions made without organizational context can create conflicting commitments. High consequence when corrected too late; business cost unquantified. | Meeting statements checked against company knowledge, evidence cards, operational actions and before/after logs. | Put policy conflicts and source evidence directly beside the decision. |
| **Incident Brain** — third in Google DeepMind category, same event | Repeated failed steps and fragmented context during an outage. High urgency, but no verified downtime reduction. | Incident event timeline, historical retrieval, proactive suggestions and post-mortem; builder describes local redaction. | Recovery and failure history should be visible, but avoid incident tooling as our main scope. |
| **Browser Brawl** — sponsor identifies the winning team at the YC Browser-Use hackathon, Feb 28–Mar 1, 2026 | Browser agents need useful adversarial traces and evaluations. Especially severe for an event about browser capability. | Two agents compete on a live page; traces become training data. Repository reports a small-model fine-tuning proof of concept. | Turn an adversarial interruption into a visible, useful result and retain its trace. Do not add training to our MVP. |
| **AutoMCP** — identified by E2B as an MCP Agents hackathon winner; exact place/category unverified | Hand-building integrations from API documentation delays useful tools. Directly relevant to an MCP event. | Fetch docs, generate server files, install/build in an E2B sandbox, return files and execution logs. | Generated code must actually run; show exit status and artifacts. Compilation alone does not prove semantic correctness. |
| **MINA** — first place, You.com Agentic Hackathon 2025 | Startup research is scattered across sources. Moderate standalone consequence, strong fit for a search sponsor. | One interface organizes sourced startup, trend and funding research. | A focused interface and credible sources can carry more value than a large agent count. |
| **DeepRadar** — second place, same You.com event | Relevant industry developments get lost in repeated news. Moderate urgency; recurring team workflow. | Filter, deduplicate and synthesize a shareable monitoring report. | Produce an artifact another person can use; avoid an unbounded research assistant. |
| **Autobelay** — first place plus Featherless prize, Alpaca AI Trading Agents Hackathon 2026 | An agent can propose actions that exceed a user's risk envelope. High consequence and excellent conceptual fit for containment. | Model proposals pass deterministic gates; only trusted code places orders. Builder reports adverse challenger results as well as a positive judged run. | Separate model suggestions from policy authority and final actions; disclose failures as evidence. |

Rank evidence for the three Olympics entries comes from the [organizer's winners announcement](https://www.linkedin.com/posts/lablab-ai_728-teams-266-ai-applications-one-week-activity-7467171942928871424-vsHH). Their implementation descriptions come from the builder submissions: [Deals Machine](https://lablab.ai/ai-hackathons/milan-ai-week-hackathon/view-1-studio/deals-machine-the-autonomous-sales-agent), [ContextGuard](https://lablab.ai/ai-hackathons/milan-ai-week-hackathon/revived/contextguard-live-decision-helper), [Incident Brain](https://lablab.ai/ai-hackathons/milan-ai-week-hackathon/ari/incident-brain-your-autonomous-co-responder).

Browser Brawl's winner designation is supported by [MiniMax's sponsor recap](https://www.minimax.io/news/minimax-ycombinator-hackathon-building-the-future-of-web); implementation details by the [builder repository](https://github.com/RichardHruby/browser-brawl). The primary sponsor source says winning team; this plan does not upgrade that to a verified overall first-place rank.

AutoMCP's designation and original Groq/E2B loop are described by [E2B](https://www.linkedin.com/posts/e2b-dev_automcp-agent-to-build-mcp-servers-on-demand-activity-7401279980141379585-JkEW). Its [current repository](https://github.com/BinSquare/autoMCP) describes install/build logs and generated artifacts; current code may differ from its judged version. Both research products' ranks and the organizer's stated strengths appear in [You.com's winner announcement](https://you.com/resources/the-winners-of-the-you-com-agentic-hackathon-2025); builder records: [MINA](https://github.com/SummerBreezeChang/MINA), [DeepRadar](https://github.com/noemit/DeepRadar).

Autobelay's rank is established by [LabLab's announcement](https://www.linkedin.com/posts/lablab-ai_alpaca-winners-announcement-activity-7511345812862541824-g50A). The deterministic gate design and challenger comparison are [builder-reported](https://lablab.ai/submissions/z2pvao27ysyqirbqo70xjqp1); we have not reproduced performance and do not treat returns as predictive evidence.

### What we can reasonably infer

The most transferable combination is **a concrete business task + actual execution + evidence that survives inspection + bounded authority**. This is our inference across cases, not a claim that these features caused selection. You.com's account explicitly praises relevance, source credibility and interface clarity; most other announcements publish results without detailed judging reasons.

For Pattern A, combine AutoMCP's execute-and-report loop with Autobelay's deterministic limits: generate an analysis program, execute it, compare its result to a trusted calculation, preserve the failed attempt if corrected. For Pattern B, combine Browser Brawl's visible adversarial moment with MINA/ContextGuard's source-backed interface. For Future of Work, apply Deals Machine's complete business flow to buying. The coherent merger is a procurement decision; a suite of unrelated agents would weaken the demonstration.

## Customer problem and competition

Initial customer hypothesis: an operations manager at a 20–200-person business buys standardized equipment from a small approved supplier list. The buyer has a deadline and spending cap but receives inconsistent quantities, shipping terms and lead times. The costly decision is selecting a plausible-looking offer that fails a hard constraint.

The broader market has supporting evidence. Deloitte's survey covers more than 250 CPOs in 40 countries and identifies siloed working as a barrier for 57% of respondents; technology capability and talent also limit execution. This supports procurement complexity, not proof that our exact small-business segment will buy QuoteProof. [Deloitte survey release](https://www.deloitte.com/us/en/about/press-room/2025-chief-procurement-officer-survey.html)

| Existing product | What its own materials establish | Implication |
| --- | --- | --- |
| Ramp Vendor Sourcing | Structured sourcing, supplier responses, pricing comparisons and AI-assisted grading in its procurement workflow. | AI comparison and workflow integration are established features. [Ramp documentation](https://support.ramp.com/vendor-sourcing-in-ramp-procurement/) |
| Zip | Procurement orchestration and purpose-built agents appear in its product material. | Enterprise coordination alone is insufficient differentiation. [Zip executive guide](https://lp.ziphq.com/rs/195-QFD-187/images/Zip_Executive_Guide.pdf?version=0) |
| PROCAI | Supplier discovery, RFQs, quote comparisons and approval workflows. | A smaller procurement assistant also faces direct competition. [PROCAI](https://www.procai.world/) |
| SourcingHQ | RFQs, comparisons and human award decisions; offers a comparison tool for existing quotes. | Human approval is a baseline feature, not our novelty. [SourcingHQ](https://sourcinghq.ai/about) |

These are first-party product descriptions, not hands-on feature audits. We cannot claim competitors lack isolation, evidence exports or injection defenses simply because the inspected pages omit them. Our demonstrable difference must be the submitted implementation: quote-to-calculation provenance, restricted execution, stale-approval rejection and a reproducible adversarial evaluation.

In this event, public team ideas already include self-healing QA ([Suture.ai](https://lablab.ai/ai-hackathons/vultr-hackathon/quezio)) and an execution firewall with self-healing analysis ([MARIA](https://lablab.ai/ai-hackathons/vultr-hackathon/maria)). Both inspected pages say there is no submission yet. This is limited overlap evidence, not a census of competitors or proof of their capabilities.

Before claiming validation, conduct three buyer conversations and two timed tasks, using actual participants and consented/redacted documents. Ask about the last bad comparison, who approves, which fields disqualify a quote and what evidence they retain. Measure manual versus assisted time and errors on comparable tasks. If no buyers participate, report a synthetic technical evaluation and leave willingness to pay unvalidated.

Pricing hypothesis for interviews: $49–149 per workspace/month or a small paid pilot. This is a proposed experiment, not a market-supported price. Do not claim measured savings, revenue, customers or an invented addressable market.

## Historical candidate scoring — withdrawn

Scores are our planning estimates, 1–5. Treat the four published criteria equally because no weights are published. Feasibility is an additional delivery lens, not an official criterion. A tenth of a point is not statistically meaningful.

| Candidate | Technology | Presentation | Business value | Originality | Criterion mean | Solo feasibility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| QuoteProof: evidence-backed buying decision | 5 | 5 | 4 | 4 | 4.50 | 4 |
| Self-healing PR/QA agent | 5 | 4 | 4 | 2 | 3.75 | 3 |
| General CSV analyst | 4 | 4 | 3 | 2 | 3.25 | 5 |
| Browser adversarial evaluation arena | 5 | 5 | 3 | 3 | 4.00 | 3 |
| Incident investigation agent | 4 | 4 | 5 | 3 | 4.00 | 2 |
| Invoice reconciliation agent | 4 | 4 | 4 | 3 | 3.75 | 4 |

QuoteProof leads because it integrates both execution patterns around one inspectable decision, gives the containment incident business meaning, and has a bounded demo. Its risks are a crowded category and browser reliability. General CSV analysis is the easiest fallback but weaker on differentiation. Invoice reconciliation is the best fallback if buyer evidence favors finance or browser access fails; preserve the same execution/evidence core and enter Pattern A only rather than presenting broken browser use.

The decision would change if the team has unusually strong incident expertise, access to a real buyer with a different urgent problem, or cannot pass the Day 1 sandbox/model spike. No existing workspace project was inspected or assumed reusable.

## Technical evidence and limits

Vultr's [inference documentation](https://api.vultrinference.com/docs) supports the supplied base URL and model discovery. The public [model catalog](https://api.vultrinference.com/v1/models) returned 35 entries during this session; selected metadata is saved in [MODEL_CATALOG_SNAPSHOT.json](MODEL_CATALOG_SNAPSHOT.json). Candidate `qwen3.8-flash-next` advertises text, image and tool support, with text prices of $0.10/M input tokens and $0.20/M output tokens. These metadata are not an authenticated capability or latency test. Recheck availability, tool schema and image behavior in the actual account before selecting it.

Docker requires explicit resource constraints; they are not supplied by containerization alone. [Docker resource documentation](https://docs.docker.com/engine/containers/resource_constraints/) gVisor narrows kernel exposure but does not replace network policy, cgroups or secure services. [gVisor security model](https://gvisor.dev/docs/architecture_guide/security/) These constraints drive the separate worker design and acceptance tests in [BUILD_PLAN.md](BUILD_PLAN.md).

The first-party compute pricing pages returned HTTP 403 to the research tool. Consequently, the budget is a spending envelope with explicit assumed hourly rates, not a verified quotation. No subscription, paid API call, resource provisioning, deployment or submission was performed.
