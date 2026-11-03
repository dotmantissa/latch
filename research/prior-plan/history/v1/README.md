# QuoteProof: Vultr Agent Rush build strategy

**Review status, November 3:** the [judge scrutiny](../../JUDGE_REVIEW.md) supersedes the initial recommendation's confidence. Verdict: **revise before advancing**. The proposed product fits the event but does not yet establish a strong overall-first case. The build plan remains a draft; validation gates are unresolved.

**Working recommendation:** build an agent that compares three supplier offers, executes the buying calculation in a disposable sandbox, and returns a recommendation whose inputs and approval can be inspected.

The demo's buyer needs 100 identical items within seven days and a $1,100 budget. The lowest advertised unit price requires buying 200; another offer arrives late. Executed arithmetic selects the $980 feasible offer. A hostile supplier page then tries to redirect the agent, while policy and isolation bound what it can do. Changing the selected quote invalidates the old approval. All offers are synthetic fixtures, clearly labeled.

Enter Blast Radius Zero using both browser and code execution. The business workflow follows the procurement direction in the organizer's broader playbook. A single challenge choice keeps the submission coherent; combined challenge eligibility is unconfirmed. [Organizer playbook](https://lablab.build/ai-hackathons/vultr-hackathon)

| Artifact | Contents |
| --- | --- |
| [RESEARCH.md](../../RESEARCH.md) | Eight winners across five comparable events, rank evidence, customer pain, competitors, candidate scoring and uncertainties. |
| [BUILD_PLAN.md](BUILD_PLAN.md) | Scope, architecture, sandbox boundaries, acceptance cases, six-day schedule, spending assumptions and demo script. |
| [JUDGE_REVIEW.md](../../JUDGE_REVIEW.md) | Independent critique, superseded scoring, concrete corrections and go/revise/reject evidence gates. |
| [DEMO_SCENARIO.json](DEMO_SCENARIO.json) | Concrete synthetic request, three offers, expected arithmetic and a changed-quote case. |
| [MODEL_CATALOG_SNAPSHOT.json](../../MODEL_CATALOG_SNAPSHOT.json) | Public Vultr catalog metadata retrieved November 3; selected candidates, prices and modalities. |

Assumptions: one engineer, fresh build, remote participation. Existing projects were not inspected. No implementation or paid deployment is included in this planning work. A top-prize result cannot be guaranteed.

The live dashboard currently closes **November 8, 2026 at 23:00 UTC**, which is **midnight entering November 9 in Lagos**. Our build plan targets submission readiness at **18:00 UTC / 19:00 Lagos on November 8**. Reconfirm the actual form and remote first-prize eligibility. [Live schedule](https://lablab.ai/ai-hackathons/vultr-hackathon/live)

First implementation step: prove one real Vultr inference call, one screenshot from isolated Playwright, one generated Python execution, and cleanup after timeout. The architecture is a proposal until these spikes and the containment tests pass.
