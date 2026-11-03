# QuoteProof: independent scrutiny of the proposed direction

Reviewed November 3, 2026. This evaluates the existing plan, not a working product. No customer task, model invocation, sandbox attack or competitor product was tested during this review. Primary event and competitor materials were reopened. The judgments below are assessments, not official scores or a forecast of placement.

## Verdict

**Revise before advancing. The current direction fits the hackathon, but the evidence does not justify treating it as a strong overall-first contender.**

The product is a plausible entry with a coherent user flow. Its central weakness is that a familiar quote-comparison feature is doing very little business work while the architecture does a great deal of engineering work. A polished implementation could satisfy the brief and still lose to a submission with a more consequential problem, a necessary agent workflow and stronger evidence of usefulness.

Retain procurement as a candidate, not as an approved winner strategy. Do not advance the existing plan unchanged. Nor does this review establish that a different candidate is better; that would require comparison using the same evidence burden.

## Correcting the previous assessment

The earlier 4.50/5 comparison was an uncalibrated planning estimate. Technology and presentation were scored as though the proposed system would work exceptionally well, while competitors and alternatives were assessed more conservatively. The result favored our own design without enough evidence. It is superseded by this review.

The winner research is useful for finding techniques, not estimating our chance of winning. It samples winners without comparable losing submissions, mixes different events, and includes sponsor-category prizes rather than exclusively overall prizes. Their judging conditions differ. Combining their features does not establish an advantage here.

The eight cases remain valid research references where their ranks were supported. The inference that their combination makes QuoteProof a top-prize candidate is not established.

## Fit for this hackathon

The event explicitly includes comparison shopping and accepts code execution or browser use; the broader playbook permits one or both patterns. Procurement is also a listed enterprise direction. Required Vultr execution and containment align with the proposed architecture. Neither using both patterns nor using gVisor has a published automatic scoring bonus. [Vultr brief](https://community.vultr.com/e/vultr-agent-rush-hackathon), [organizer playbook](https://lablab.ai/ai-hackathons/vultr-hackathon)

| Lens | Assessment of the planned version | Reason |
| --- | --- | --- |
| Use-case eligibility | Strong conceptual fit | A sandboxed comparison agent is expressly within the brief. Eligibility of the team and completeness of deliverables are separate questions. |
| Application of Technology | Mixed; unvalidated | Isolation is relevant, but generated arithmetic duplicates a reference calculator and the agent could become a fixed script around fixture pages. No deployed capability is proved. |
| Presentation | Good potential; unvalidated | MOQ, delivery and stale approval are understandable. A long security interlude could overwhelm a very small buying task. |
| Business Value | Plausible, weakly evidenced | No direct buyer evidence, task baseline, error-cost evidence or willingness to adopt. Broad procurement surveys do not establish the exact workflow. |
| Originality | Weak in its current form | Comparison, sources and approval exist elsewhere. The concrete advantage over them is not demonstrated. |
| Containment substance | Sensible proposed controls, insufficient proof | A process timeout is narrower than resistance to a poisoned recommendation or unauthorized action. |
| Six-day deliverability | High risk for the whole plan | The system includes two execution environments, a supervisor, egress policy, validation, durable state, approvals, evaluation and public deployment within an assumed 48 hours. |
| Overall first-prize case | Not yet strong | A strong match to the examples establishes relevance, not a reason to rank it first. No comparison against the eventual field is available. |

Do not calculate a probability or an aggregate score from this table. There is no running submission, known full competitor field or calibrated judging model.

## Findings and concrete corrections

### 1. The business task is too small to justify the proposed machinery — critical

**Judge objection:** “Why did you create generated code, a validator and several sandboxes to compare three offers using a formula I can put in a spreadsheet?”

The current one-item example checks MOQ, shipping, budget and lead time. These are legitimate constraints, but all arithmetic and selection rules are already completely specified by trusted code. Generated Python adds failure modes and latency without establishing additional customer capability. Running and then correcting generated code can look like creating an error to showcase a retry loop.

There is a structural tension: if the reference program completely computes the correct decision, it can produce the recommendation directly. If it checks only partial invariants, it cannot certify a general generated analysis. Calling it a full verifier without defining that boundary would overclaim.

**Required correction:** keep the authoritative calculation deterministic. Either lead with Pattern B and drop generated calculation as a headline, or identify a real buyer task requiring variable analysis that cannot be served by the existing fixed formula. Candidate examples are normalizing inconsistent units or producing a user-requested cost sensitivity analysis, but those must come from a real task. Generated supplemental analysis must not determine purchase eligibility outside the trusted policy checks. Do not manufacture complexity just to justify Pattern A.

**Pass evidence:** demonstrate the useful capability or measurable effort reduction that disappears when the generative layer is removed. If none exists, simplify the architecture and reassess whether the remaining product is competitive enough.

### 2. Familiar features are being treated as differentiation — critical

Ramp describes AI-assisted sourcing and quote extraction. PROCAI describes quote comparison, source documents embedded in exports, and purchase approval workflows. SourcingHQ also offers comparisons and human award decisions. [Ramp](https://support.ramp.com/vendor-sourcing-in-ramp-procurement/), [PROCAI comparison](https://www.procai.world/quotation-comparison), [PROCAI workflow overview](https://www.procai.world/), [SourcingHQ](https://sourcinghq.ai/about)

Those first-party descriptions are sufficient to challenge a novelty claim, but do not establish the quality of those products or prove that they lack our proposed security controls.

Screenshots, code logs, exact-draft approvals and containers could make our implementation inspectable. They do not by themselves establish a unique product or a buyer's reason to switch. Security configuration is especially unlikely to carry originality if all participants are required to contain execution.

**Required correction:** write one narrow, demonstrable claim about an operational failure that the product handles particularly well. For example: “The buyer can inspect a constraint-changing quote revision and cannot reuse an approval for the old terms.” Treat that as an implementation claim, not a claim that no competitor can do it. Define a repeatable evaluation showing the benefit relative to a practical baseline.

**Pass evidence:** a concrete observable advantage over manual comparison or an ordinary extraction-plus-calculator workflow, with a credible account of why the buyer values it. Merely adding more infrastructure does not pass.

### 3. Containment does not establish that the recommendation is correct — critical

**Judge objection:** “The host survived, but did the agent still choose the supplier the attacker wanted?”

An offline program can safely compute the wrong answer from a poisoned unit price. The sandbox does not establish whether the model interpreted “per pack” correctly, omitted a condition, accepted a forged claim or matched the wrong SKU. A second model reading the same page may repeat the same error. An infinite loop proves one resource boundary; a denied external request proves one network or tool policy. Neither proves decision integrity.

gVisor itself distinguishes kernel exposure protection from the rest of application security, including network policy and resource controls. [gVisor security model](https://gvisor.dev/docs/architecture_guide/security/)

**Required correction:** evaluate three separate outcomes: host/resource containment, action authorization, and decision correctness. Poison fields and supporting prose, not just instructions to send data to a forbidden domain. Bind critical extracted terms to visible source evidence; conflicting/unknown terms require review. Human confirmation is acceptable but its time must count in usability measurements.

**Pass evidence:** preserve the actual model request and policy decision; demonstrate an adversarial recommendation case, an unauthorized-action attempt and a bounded resource-abuse case. Report incorrect recommendations even when the infrastructure behaved correctly. Avoid “prompt-injection proof” and “zero risk.”

### 4. The curated demonstration does not establish usefulness on unfamiliar inputs — high

The same team controls the pages, layout, terms, ground truth and expected winner. This is appropriate for a regression case, but weak evidence of generalization. If all controls work only with fixed page tokens and known selectors, the product may be a safe fixture runner rather than a useful supplier assistant.

The current fallback also has a presentation trap: removing arbitrary URLs protects reliability, but narrows the product's advertised promise. Restrictions are defensible only if useful supported workflows remain.

**Required correction:** retain fixtures for attacks and regression; include at least one source set not designed by us, within a clearly stated supported format. Use consented redacted buyer quotes or appropriately accessible public supplier materials. Freeze source snapshots and expected terms before tuning; include a held-out layout or source revision. No bypassing logins or anti-bot restrictions is required.

**Pass evidence:** a reviewer can supply a different supported request or quote and obtain a correct result or justified review response. A specific page adapter is acceptable; a fixed answer or unexplained new-layout failure is not. Do not relabel a snapshot replay as live browsing.

### 5. The strongest commercial pain has been assumed — high

**Judge objection:** “Who needs this often enough to use it, and what do they do today?”

The plan assumes a buyer at a 20–200-person business and proposes pricing without interviewing that buyer. In the example, we perform a one-item comparison a competent buyer can inspect quickly. The real burden may instead be obtaining quotes, matching many line items, verifying scope or getting approval; our exclusions may remove most of that burden.

Public product descriptions support the existence of a procurement software category. They do not establish demand for this particular public-page workflow or our suggested subscription price.

**Required correction:** anchor the product to one observed repeated buying task and its final deliverable. Obtain one authentic, consented/redacted packet if available. Measure the current task and assisted task, including correction and review time. Ask what would cause the buyer to abandon their current process. If access is unavailable, label all business value as a hypothesis and reduce the confidence of the competitive verdict.

**Pass evidence:** a named user role, observed task frequency/burden, meaningful error consequences and actual use of the resulting artifact. Small samples are discovery evidence; do not inflate them into broad market proof. Commercial validation helps a winner case but is not stated as a mandatory event requirement.

### 6. Stale approval protection has an unresolved freshness boundary — high

The plan rejects an approval after a new quote version is recorded. It does not specify how it discovers that the supplier changed the live quote. The saved screenshot and its hash can remain consistent indefinitely while the external offer changes.

Because the MVP exports a draft rather than placing a real order, approval also prevents a less consequential event than the pitch might imply. Adding a confirmation dialog before a download is not equivalent to controlling purchasing authority.

**Required correction:** decide what the product promises. For an export, show capture time, expiry and “based on captured terms”; require acceptance of material edits. For a controlled final write, recheck relevant structured terms immediately before action, compare price/quantity/availability/destination, and require new approval on material change. A recheck still does not create an atomic guarantee over an external supplier's checkout. Keep final test actions on an owned fixture and label their business consequence accurately.

**Pass evidence:** an external/fixture revision occurs without manually updating the internal quote, and the specified freshness check catches it. Otherwise narrow the claim to version-bound approval of a captured draft.

### 7. The build budget spends too much time proving infrastructure relative to value — high

The 48-hour plan includes hardened browser execution, offline generation, a separate validator, persistent jobs, artifact authorization, network edge cases, multi-session isolation, approvals, 30 evaluation runs and presentation. Each component is reasonable, but the combined delivery assumption has not been tested. Promising broad URL support and robust egress policy simultaneously is especially risky.

**Required correction:** choose a single primary execution pattern and one supported source workflow; retain the controls necessary for that boundary. Defer optional fixture writes and duplicated generation until a useful end-to-end flow works. Do not cut required isolation or resource caps to rescue the schedule. A schema-validating bounded browser adapter can still be agentic if the model actually plans supported steps and responds to observations.

**Pass evidence:** the intended Vultr model, runtime and browser work together in a narrow technical spike, with observed latency, cleanup and failure recovery. Until then, both implementation confidence and the hour estimate remain low-confidence assumptions.

### 8. The evaluation target can hide dangerous failures behind a good average — high

“90% field extraction” is inadequate as a purchasing decision metric. An agent could correctly extract supplier names and descriptions while misreading the one number that reverses the decision. Conversely, abstaining on every case would look safe while providing no value.

Thirty runs of ten scenarios mostly repeat the same ten situations; they are not thirty independent demonstrations of generalization. A test split used repeatedly for tuning becomes development data.

**Required correction:** separately report critical-field fidelity, correct eligibility/ranking, unsafe recommendation rate, review/abstention rate, useful task completion, user correction time and latency. Evaluate baseline and adversarial variants separately. Have expected answers checked independently before testing; reserve held-out inputs for the final evaluation.

**Pass evidence:** zero known unsafe recommendations on the finite release suite, all critical errors blocked or reviewed, and a useful completion rate high enough to beat the measured baseline. Do not use a universal safety claim or hide low completion by excluding review cases. “Zero observed” is not a statistical guarantee.

## The strongest version worth validating

Retain the working name, but narrow the product to **a procurement decision verifier for a specific buyer workflow**. The primary output is a decision packet showing supported source terms, deterministic constraint checks, uncertainty and version-bound human acceptance. Sandbox behavior is observable and tested; it is part of the product's reliability rather than its entire value proposition.

This is a candidate correction, not an approved new build plan. It adds no ERP, real checkout, broad supplier search, negotiation, blockchain or model training. Do not add those to compensate for weak differentiation.

The three-offer $980 example can remain an introductory explanation. It should not be the sole evidence for technical depth, market value or unseen-input capability. A richer task is justified only when it corresponds to observed buyer work; a longer synthetic spreadsheet alone does not solve the problem.

## Go / revise / reject gates

These are our internal selection gates, not event rules. They must be met before calling the revised direction a strong top-prize contender; not every gate must be evaluated by provisioning a complete application.

| Gate | Minimum evidence | Status now | If unmet |
| --- | --- | --- | --- |
| Buyer value | One authentic supported task; measured or directly observed baseline; a useful final artifact; actual buyer feedback where obtainable. | Unmet | Reconsider problem selection rather than add features. |
| Necessary intelligence | A specific benefit over fixed extraction/calculation, or a simpler browser-led design whose useful adaptation is demonstrated. | Unmet for the proposed generated arithmetic | Remove redundant code generation; reassess the remaining direction. |
| Differentiation | One precise, testable operational advantage and a baseline comparison; no unsupported competitor-absence claim. | Unmet | Do not approve the overall-first positioning. |
| Non-fixture correctness and enforcement | Unfamiliar supported inputs; honest abstention and completion metrics; separate recommendation, action and resource tests. | Unmet | Narrow claims, fix evidence or reject the direction. |
| Deliverability | Narrow Vultr model/runtime spike, measured path, honest scope and adequate time left for presentation and a public app. | Unmet | Cut optional patterns/actions or select a simpler candidate. |

Remote top-prize eligibility, exact submission requirements and prize/track structure remain external questions. They affect prize eligibility but do not repair the product weaknesses above. No organizer outreach occurred in this review.

**Final decision:** QuoteProof survives as a relevant candidate, not yet as a defensible overall-winner commitment. The next justified work is a short evidence-validation pass and scope correction, not another large layer of architecture or implementation planning. If the buyer-value and differentiation gates cannot be met, replace the direction and scrutinize alternatives by the same standard.
