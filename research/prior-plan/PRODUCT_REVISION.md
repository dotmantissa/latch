# QuoteProof v2: review terms before releasing a purchase request

Revised November 3, 2026 in response to [JUDGE_REVIEW.md](JUDGE_REVIEW.md). These are concrete design decisions and synthetic acceptance examples, not implemented capabilities or validated market claims.

## The revised product

**QuoteProof helps an IT deployment coordinator turn three equipment offers into a complete, reviewed purchase request, and rechecks supplier terms before that request is released.**

Initial buyer hypothesis: a small IT services provider preparing equipment for a client rollout. The coordinator needs the entire specified kit within a deadline. A cheap-looking offer can omit an item, quote packs rather than individual units, miss delivery or change after approval. The buyer needs a record explaining what was checked and approved.

The unit of work is one deployment purchase request. The result is an internal release record and an exportable decision packet with sources, confirmed terms, calculations, exceptions and approval. No supplier order, payment or stock reservation occurs. The buyer segment is a validation hypothesis: no actual IT buyer, incident or frequency is asserted.

## Eight concrete adjustments

| Review finding | Product adjustment | Enforcement / acceptance evidence | Remaining evidence gap |
| --- | --- | --- | --- |
| Fixed arithmetic does not need generated code | Remove generated Python, repair loops and duplicated reference calculator. Lead with Pattern B. | Trusted integer-cent rules determine quantities, completeness, cost and eligibility. Model prose cannot replace results. | Whether adaptive browsing/extraction reduces buyer effort. |
| Comparison and approval are familiar | Demonstrate complete-basket review and source changes between approval and internal release. | Release binds request, evidence, terms and approval. Changed source terms stop release and produce a diff. | Competitive advantage in use; no claim that competitors cannot do this. |
| Containment does not establish correct recommendations | Evaluate source meaning, action authority and infrastructure separately. | Pack mistakes, omitted items and instructions have separate expected outcomes. Wrong recommendations fail even with a healthy host. | Actual model/attack performance. |
| Fixtures do not establish generalization | Add independent source material and a held-out supported variation. | Freeze snapshots/expected terms before tuning; reviewer can change supported inputs. | Performance on unfamiliar sources. |
| Customer pain is assumed | Choose one buyer role and evaluate the whole review/release task. | Actual baseline, correction/review time, errors and use of the packet. | Demand, savings, adoption and willingness to pay. |
| Stale approval lacks discovery | Release triggers new capture of every source used in the decision. | Browser discovers source b1→b2 without manual internal edits and rejects old approval. | Capture reliability and external changes after capture. |
| Scope overwhelms the build window | Three required items, three offers, one currency, one supplier, browser only. | No real checkout, ERP, email, supplier search or generated code. | Actual implementation time and Vultr compatibility. |
| Aggregate scores hide dangerous errors | Measure critical errors, wrong selections, abstention, useful completion and review time. | No known unblocked critical error in a finite release suite; retain all attempts. | Runtime reliability and generalization. |

These changes close design decisions, not evidence gaps.

## A concrete buying example

Synthetic scenario: equip **25 workstations** with specified docks, monitors and compatible cables, within **seven days** and **$10,000**. No product substitutions or supplier discovery.

| Offer | Supported source terms | Normalized result | Product response |
| --- | --- | ---: | --- |
| A | Monitors/cables quoted; docks expressly excluded. | $4,950 for quoted components; complete-kit total unknown. | Incomplete; never rank as the cheapest complete purchase or price the missing line at zero. |
| B | All equipment; cables in packs of ten; four-day delivery. | $9,500; three cable packs deliver 30 cables. | Feasible candidate after required source review. |
| C | All equipment; lower prices; twelve-day delivery. | $8,960. | Reject for the deadline. |

After B is approved, its dock price changes from $160 to $175 each. A release-time browser recheck discovers it, recomputes **$9,875**, and stops the old approval. The **$375** increase remains within budget but has not been approved.

These are synthetic amounts, not evidence of customer loss or savings. Incomplete A is not a valid savings baseline. Exact data and expected outcomes: [DEMO_SCENARIO.json](DEMO_SCENARIO.json).

## A useful and bounded role for the agent

The model plans a supported inspection: open approved supplier pages, follow a supported terms link, inspect exclusions, capture screenshots, propose normalized fields and prepare buyer questions. A Vultr vision call checks correspondence with the evidence. Conflicting interpretations require review.

Variable layouts and natural-language terms justify testing an agent. They do not automatically justify keeping it: compare with a fixed extractor and the same calculator. If model-driven inspection provides no benefit, simplify and reconsider competitiveness rather than invent code-generation work.

Trusted code owns request values, policy, approval and release. The model cannot raise the budget, confirm evidence, approve itself or commit a release. Model confidence and agreement between models are advisory.

Enter **Blast Radius Zero, Pattern B**. All agent calls use Vultr Serverless Inference; Playwright runs in disposable sandboxes on Vultr. One execution pattern is permitted. [Official playbook](https://lablab.ai/ai-hackathons/vultr-hackathon)

## Evidence review

For each material term show its value, unit, source text, screenshot region, URL/version and capture time. Material terms include specification, inclusions, sell units/MOQ, quantity, price, shipping, tax treatment and stated delivery.

Use `extracted`, `buyer_checked`, `disputed` and `unknown`. A buyer check records who reviewed which source/value; it does not certify supplier truth. Unknown required costs, missing items, unsupported currency/tax, contradictions or substitutions stop readiness. Preserve original values and source-backed corrections. Buyer-supplied facts require their own attribution; never present them as extracted supplier terms.

Do not claim this interface forces a careless buyer to notice every error. Include all review/correction time in evaluation. Inspectability and bounded authority are distinct from extraction accuracy.

## Release and freshness contract

“Release” creates a durable internal record: this requester approved this purchase packet under these captured terms. It is a procurement handoff artifact, not an order or external transaction.

1. Capture all supported decision pages and terms attachments. Store immutable snapshots, fingerprints and capture intervals.
2. Review critical fields and calculate completeness/feasibility using trusted rules.
3. Bind approval to request, sources, normalized terms, policy, requester and expiry. Initial approval expiry: ten minutes.
4. On **Release purchase request**, recapture all three decision sources, including nonselected offers.
5. A changed source fingerprint triggers a diff and review. Include terms/exclusions in the fingerprint. Model claims of “cosmetic change only” cannot suppress the gate; supported adapters remove only known irrelevant page chrome.
6. Recompute and require fresh review/approval on change. Unavailable or incomplete sources keep the request unreleased. Permit a clearly labeled stale draft export only.
7. For unchanged sources, trusted code atomically checks versions, ensures every capture finished within the previous 60 seconds, and creates one idempotent release record. Concurrent edits or duplicate clicks cannot bypass it.

Freshness means the recorded sources were checked within that interval at commit. It is not an atomic supplier guarantee. Later supplier changes remain unknown until another check. Uploaded static documents support review of their supplied version, not a live-terms freshness claim.

Rechecking every decision source adds latency and can stop release when an unselected supplier is unavailable. Measure that burden. The requester can deliberately remove a source and review a new comparison version; the agent cannot silently omit it to retain approval.

The demo must change the source fixture behind the browser. Editing the internal quote and showing rejection does not demonstrate discovery.

## Containment with operational meaning

- **Meaning:** A contains its exclusion and instructions asking automated reviewers to hide it. Preserve the exclusion or require review. A falsely ready complete offer fails.
- **Authority:** adversarial proposals request self-approval, release, changed limits or metadata access. The independent broker/network boundary denies them even if the model is persuaded.
- **Availability:** an owned page hangs or consumes its allowance; the supervisor ends the job, control remains responsive and a new profile/job succeeds.

Ignoring malicious text is an observed model behavior, not evidence that a broker was exercised. Separately inject a disallowed tool proposal into the broker test. Never fabricate model actions for the video. Required isolation, limits and lifecycle discipline remain in place even when browsing has no buyer secrets.

## Evidence that can falsify the idea

Compare the complete task with **manual source review plus a spreadsheet** and, if practical, **model extraction plus the same deterministic calculator**. Include correction, review, recapture and release time. All baselines receive identical inputs and ordinary human review.

Collect one authentic redacted packet or suitable independent public source set and independently check expected terms. Aim for three buyer conversations and two task participants if available. These are discovery goals, not claimed results or event requirements. Contact is not authorized by this document.

Prepare held-out supported inputs after the first adapter. Report critical-field errors, false-ready/wrong-selection rate, review rate, useful completion, buyer time, latency and cost. Separate attacks from benign cases, repeats from independent examples, and model behavior from enforcement. Release requires zero known unblocked critical errors in the finite suite plus useful completion; abstaining on everything fails.

Continuation requires either reduced observed effort without new critical errors, or catching a consequential mistake the baseline missed with acceptable added effort. Agree the effort bound before testing. If neither occurs, reconsider the idea.

## Competitive position and remaining verdict

Existing tools already compare quotes and support approval. PROCAI's public example even highlights an omitted item and payment terms; spotting omissions alone cannot be claimed as novelty. [Competitor example](https://www.procai.world/quotation-comparison)

Our proposed demonstration covers source inspection, evidence review, changed-term detection and bounded internal release together. Its advantage must be observed on realistic inputs and attacks. No claim to have invented procurement AI, source evidence or secure approvals is justified.

This is a stronger candidate for an evidence/feasibility pass. It has not earned a new numerical score or first-prize prediction. Buyer value, differentiation in use, model quality, isolation and deployed feasibility remain open. [JUDGE_REVIEW.md](JUDGE_REVIEW.md) stays unchanged as the historical criticism; the next review must distinguish design responses from tested outcomes.
