# Anti-Patterns

**Audience:** anyone reviewing a `plan.md`, `tasks.md`, or PR for conformance to the constitution. Especially `/speckit.analyze` reviewers.

This is a catalog of patterns each constitutional principle exists to reject. Spotting one in a design proposal is a fast signal that the design is in conflict with the [constitution](../../constitution.md). The constitution is the law; this document is the field guide.

If a pattern below appears in a proposal, it does **not** automatically mean the proposal is wrong — only that the proposer must explicitly justify why this case is different. "It will be fine" is not a justification; "the failure mode the principle exists to prevent does not apply here because…" is.

---

## I. Evidence Over Assertion

| Anti-pattern | Why it fails |
|---|---|
| **Model-confidence verdicts.** Promoting a finding to `true-positive` because the model rated its confidence high. | Model confidence is not predictive of correctness; the same fluency that produces correct claims produces fabrications. |
| **"High-confidence findings can skip the gate."** | The first carve-out reintroduces the failure the gate was added for. Every relaxation we tried, we reverted. |
| **Citations not mechanically resolved.** Treating a cited code location as evidence without verifying it points to real code at verdict time. | LLMs cite plausibly. The check is not "did the model cite something?"; it is "does the citation resolve?" |
| **Trust-boundary citations satisfied by prose.** "The user input enters at the API boundary" without a code citation. | Prose cannot be verified. A path-and-symbol citation can. |
| **Carving out vulnerability classes from the gate.** "We don't require evidence for [class] because they're obvious." | Carve-outs accumulate. The narrow [FR-087a](../../spec.md#73-evidence-gate) carve-out is the only acceptable form, and it is enumerated. |

---

## II. Surface Only What Survives

| Anti-pattern | Why it fails |
|---|---|
| **Issue per detection.** Posting every Detector candidate to the issue tracker. | Buries reviewers in noise; trains them to ignore the channel; real findings drown. |
| **"Surface low-confidence findings as a separate label."** | Defeats Principle II by re-introducing the noise channel under a new name. |
| **Notifications on every triaged finding regardless of verdict.** | Reviewers notice false-positive notifications and silence the channel for true-positives too. |
| **Direct issue-tracker writes from the Detector.** | Forbidden by [FR-044](../../spec.md#54-detector); the Detector writes only to the internal store. |
| **Discarding rejected findings.** "If it's a false-positive, why keep it?" | Rejected findings are evidence that "we already looked at this." Discarding them re-runs the same triage on every re-evaluation. |

---

## III. Liveness By Heartbeat, Never By Clock

| Anti-pattern | Why it fails |
|---|---|
| **Wall-clock timeout to reclaim a claim.** "Agent has held this for 30 minutes; reclaim." | Cannot distinguish "hung" from "waiting on rate-limited upstream"; produces a treadmill of healthy agents being killed mid-work. |
| **Heartbeat on the same event loop as primary work.** | A CPU-bound moment makes a healthy agent miss beats; the substrate kills it. |
| **Heartbeat that requires the agent to call back into its own state.** | If the agent's main lock is held, the heartbeat fails. The lane must be independent. |
| **Conflating session rotation with liveness.** Treating the session-rotation hard limit ([FR-118](../../spec.md#95-agent-lifecycle-limits)) as a liveness signal. | Session rotation is a deliberate cost-control rotation of a heartbeating agent's session; it must not reclaim claims. |

---

## IV. Claims Are Atomic And Mortal

| Anti-pattern | Why it fails |
|---|---|
| **Cooperative locks** ("write a claim record; trust agents not to overlap"). | Two agents can claim the same task within a small window. Last writer wins. Reasoning is lost. |
| **Operator-only unlock.** "If a claim is stuck, an operator manually releases it." | Crashes happen overnight. Operators sleep. Stranded work piles up. |
| **"Next agent breaks the lock if it looks stale."** | Produces both stranded and duplicate work depending on timing. |
| **Process-supervisor-only release** (no substrate-level mortality). | The process supervisor can itself wedge. Substrate-level liveness-tied release is required. |
| **Releasing a claim by deleting its record without a transaction.** | Concurrent claim attempts can race the delete; classic TOCTOU. |

---

## V. The Provider Is The Rate Arbiter

| Anti-pattern | Why it fails |
|---|---|
| **Static internal cap below the provider's stated quota.** "Be a good neighbor; cap at 80%." | The real burst limit is rarely the stated quota. Below-real-limit caps leave paid capacity idle and mask the provider's signal. |
| **Per-agent backoff state.** Each agent maintains its own backoff timer. | N agents independently rediscover the same limit N times. |
| **Hardcoded rate limit numbers in the agent code.** | Drifts from reality; updates require redeploy. |
| **Throttling based on a derived metric** (CPU, memory, queue depth). | These do not measure provider capacity; they measure local symptoms. |
| **Suppressing 429s** ("retry silently and never log"). | Hides the signal Principle V is built around. The 429 *is* the information. |

---

## VI. Coverage Before Yield

| Anti-pattern | Why it fails |
|---|---|
| **Auto-stop on yield alone.** | Fires on the first dry spell, which on a hard target is the beginning, not the end. |
| **Auto-stop on runtime alone.** "We've been running 4 hours; stop." | Says nothing about whether the work was done. |
| **Treating model-emitted "I'm done" as the done signal.** | The model is not authoritative on coverage. The Coverage-Guide is. |
| **Counting coverage by "agents have run" rather than "checklist items attempted."** | Every agent could be running and the checklist could be untouched. |
| **Marking coverage complete to satisfy yield-stop.** | Defeats the conjunction. The coverage flag must reflect substrate state, not be set as a workaround. |

---

## VII. Exploited Means Demonstrated

| Anti-pattern | Why it fails |
|---|---|
| **The agent that wrote the POC sets `exploited`.** | Same incentive failure as a human grading their own work. |
| **`exploited` set on debugger-only repro.** | Not the headline impact; not what reviewers think the label means. |
| **`exploited` set on "the payload was accepted."** | Acceptance is not impact. |
| **`exploited` set because a similar issue elsewhere was exploited.** | Prior art is not present demonstration. |
| **`exploited` inferred from evidence quality.** | Inference is not demonstration; the flag has a one-sentence definition for a reason. |
| **Removing the testbed and "still setting `exploited` based on judgment".** | Without a testbed, the flag cannot be set, period. Document the limitation in your spec. |

---

## VIII. Fingerprints Are Stable Under Edit

| Anti-pattern | Why it fails |
|---|---|
| **Including line numbers in the fingerprint.** | Any nearby edit re-files the same finding as new. |
| **Including a snippet hash in the fingerprint.** | Whitespace, formatting, and refactoring all break the hash. |
| **Including the detection timestamp in the fingerprint.** | Guarantees non-stability. |
| **Fingerprinting by issue-tracker ID.** | The fingerprint is upstream of the issue tracker; the tracker keys *on* the fingerprint. |
| **Generating a new fingerprint on re-triage.** | Re-triage replaces the verdict, not the identity. |

---

## IX. Sandbox By Infrastructure, Not By Prompt

| Anti-pattern | Why it fails |
|---|---|
| **Prompt-level network rules as the only boundary.** "We told the agent not to call external hosts." | Agents read untrusted content; that content can contain instructions. The boundary must be unarguable. |
| **"The agent will not write to /etc because we told it not to."** | Same problem; instructions in the target's content can override. |
| **A sandbox that "should" block egress** (no verification ritual). | If you have not run a curl from inside the sandbox to confirm it is blocked, the boundary does not exist. |
| **Allowlisting "dev/test domains" without scrutiny.** | An allowlisted host can become a pivot to anything that host can reach. |
| **Read-write mounts of target source.** | A prompt-injected agent can corrupt the target. The mount must be read-only. |

---

## X. The Operator Outranks Every Agent

| Anti-pattern | Why it fails |
|---|---|
| **Treating peer messages as commands.** "Another agent said X is saturated, so I will skip X." | Agents talk each other out of work; one bad note infects the fleet. |
| **Treating prior-agent persistent notes as fact.** | Notes are records of what an agent attempted, not truth. |
| **Coverage flag set by an agent's claim that "this area is done."** | The flag is set from substrate state, not from agent prose. |
| **Auto-merging Self-Improver-proposed rules.** | Removes the operator's authority over the rule corpus. |
| **Auto-applying Remediator-proposed patches.** | Same problem; operator authority is over merge, not over draft. |

---

## XI. Persist Atomically

| Anti-pattern | Why it fails |
|---|---|
| **Delete-then-write.** Removing an index file before writing the new one. | A crash between the steps leaves readers with nothing and no error. |
| **Truncate-then-write.** | Same failure mode; readers see an empty file. |
| **Multi-key updates without a transaction.** | A crash mid-update leaves an inconsistent record set. |
| **"We rarely crash; we'll skip the atomic step."** | The seed authors lost multi-hour index builds to deploy-time terminations. Rarely is enough. |
| **Atomic for some artifacts but not others.** | Failure happens on whichever artifact you skipped. The rule is general for a reason. |

---

## How to use this catalog in review

1. Read the proposal (plan, task, code change, or PR description).
2. Scan the tables above for any of the rejected patterns.
3. If you find one, ask: "what failure does this pattern reproduce, and why does the proposer believe it does not apply here?"
4. If the answer is convincing, document it; the proposal may be sound.
5. If the answer is "it will be fine," reject and link this page.

The constitution does not require you to be creative. It gives you the conclusions of past experiments. This catalog is a quick index into them.

## See also

- [`../../constitution.md`](../../constitution.md) — the canonical principles.
- [`../reference/principle-fr-matrix.md`](../reference/principle-fr-matrix.md) — which FRs enforce which principle.
- [`../governance/amendment-process.md`](../governance/amendment-process.md) — how to propose changing a principle if you genuinely have a case.
