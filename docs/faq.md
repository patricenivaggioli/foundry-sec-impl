# FAQ

**Audience:** anyone evaluating the seed for adoption who has questions the README does not directly answer.

Each answer cites the canonical artifact ([`spec.md`](../spec.md), [`constitution.md`](../constitution.md), [README](../README.md)) rather than restating it. If an answer here disagrees with a canonical artifact, the artifact wins; this page is updated.

---

## Why is there no code?

Because the value of what we are open-sourcing is the **design**, not our implementation of it. Our internal systems are tightly coupled to Cisco's infrastructure (cloud provider, issue tracker, LLM gateway, deployment platform, severity taxonomy). Open-sourcing that code would give you something that runs in exactly one environment: ours.

What transfers is the *design*: which agent roles you need and why, what each must guarantee, how findings flow from detection to publication, what "done" means for an evaluation, where the quality gates go, and which shortcuts will hurt you six months in. That design is infrastructure-neutral.

See README [§"Why we're releasing a spec instead of a tool"](../README.md#why-were-releasing-a-spec-instead-of-a-tool).

## Can I skip the constitution?

No. From [`constitution.md` §Precedence](../constitution.md#precedence):

> Where this constitution and `spec.md` conflict, this constitution wins and `spec.md` is in error. Where this constitution and a generated `plan.md` or `tasks.md` conflict, the plan or tasks are in error and `/speckit.analyze` should flag it.

Each principle exists because the seed authors shipped a system without it and broke. Skipping the constitution reproduces those failures.

You may, of course, decline to adopt the seed at all. But if you adopt the seed, the constitution comes with it.

See [`docs/principles/anti-patterns.md`](principles/anti-patterns.md) for the failure modes each principle exists to prevent.

## Do I need CodeGuard specifically?

No. From the README's [Companion: CodeGuard](../README.md#companion-codeguard) section:

> CodeGuard stands on its own and predates this work; you can run Foundry with a different rule format. What Foundry adds is the machinery that turns a rule corpus from a maintained artifact into a self-improving one.

What you do need:

- A versioned, independently-maintained rule corpus ([FR-041](../spec.md#54-detector)).
- A rule format the Detector's LLM-evaluated check can apply per function with caller/callee context.
- A way to record rule-gap entries ([FR-042](../spec.md#54-detector)) that can later be generalized.

CodeGuard satisfies all three. So might a homegrown format. The seed does not pick.

## What if I have only 2 of the 8 core roles staffed?

The seed describes 8 core roles, each catching the previous role's failure mode. If you cannot staff all 8 (in the human sense — building, owning, and operating each), you have two options:

### Option 1: stage by role

Build Indexer + Detector first; defer Triager / Validator / Reporter until later. Document explicitly that during the staging period:

- Detection candidates accumulate in the internal store ([Principle II](../constitution.md#ii-surface-only-what-survives) is satisfied — they are not surfaced).
- The system produces no surfaced findings; this is correct, not broken.
- The "evaluation done" signal does not exist yet.

This matches the seed's design. You are not deviating; you are not yet complete.

### Option 2: merge roles

In `/speckit.clarify`, the Identity & scope section asks whether to merge / split / omit core roles ([§4.2 marker](../spec.md#42-the-eight-core-roles)). For a small team, merging Triager + Validator into one role is a valid answer, as long as the merged role still assigns Triager verdicts and performs Validator reproduction and `exploited` handling where a testbed is configured.

What you cannot do: skip a *responsibility*. Even merged, the merged role must perform both functions. Specifically the evidence gate ([§7.3](../spec.md#73-evidence-gate)) and the `exploited` requirement ([Principle VII](../constitution.md#vii-exploited-means-demonstrated)) remain.

See [`docs/adoption/clarification-playbook.md`](adoption/clarification-playbook.md) Group A.

## How do I know my clarification is complete?

When all of the following are true:

- `/speckit.clarify` reports no outstanding markers.
- A manual read of `spec.md` finds no template-language phrases ("the chosen X", "an appropriate Y").
- `/speckit.specify` runs cleanly and reports no constitutional conflicts.
- `/speckit.analyze` passes.
- Every Group A and Group B box on [`docs/reference/open-questions-checklist.md`](reference/open-questions-checklist.md) is ticked.

Tools assist; they do not certify. The manual read pass is a deliberate part of the workflow.

## What's the relationship between FRs and Constitution principles?

The principles are **inviolable invariants** that any implementation must uphold ([`constitution.md` §Purpose](../constitution.md#purpose)).

The FRs are the **specific requirements** the seed imposes to enforce the principles in concrete terms. Most FRs implement a principle; some FRs are operational details of the system shape.

The mapping is documented in [`docs/reference/principle-fr-matrix.md`](reference/principle-fr-matrix.md). The constitution's [Compliance review](../constitution.md#compliance-review) requires every principle to have enforcing FR coverage (no GAP rows).

## Can I use a different LLM provider mid-evaluation?

The seed does not forbid it, but [Principle V](../constitution.md#v-the-provider-is-the-rate-arbiter) makes it operationally harder. Each provider has its own backpressure signal; mixing providers requires you to preserve per-provider adaptive backoff. Multi-provider abstractions that "load-balance" usually break Principle V.

If you must, use one provider per evaluation run, not per agent.

See [`docs/adoption/integration-decisions.md` §11.2](adoption/integration-decisions.md#112-llm-provider).

## Can I run the system without a testbed?

Yes. The trade-off is explicit in [`spec.md` §11.12](../spec.md#1112-testbed) and [Principle VII](../constitution.md#vii-exploited-means-demonstrated): without a testbed, the Validator cannot independently reproduce findings, so `exploited` cannot be set.

- **IMPORTANT**: Without a testbed, findings may carry lower review confidence because independent runtime reproduction is not possible. Reviewers may find a higher number of false positives, especially for issues whose exploitability depends on runtime behavior.

You can still produce confirmed `true-positive` findings when the Triager evidence gate is satisfied. The Validator still produces a PoC artifact without running it ([FR-066](../spec.md#56-validator)), but it cannot set `exploited=true` or prove runtime impact. Document the limitation in your spec. For Generative AI this hits harder since model behavior is stochastic and only verifiable empirically.

## The seed says "exploited" is the strongest signal — but my reviewers don't filter on it. What now?

Two possibilities:

1. **Your reviewers are not yet using it.** Educate them; show them findings with vs without the flag. The flag's value comes from disciplined enforcement of [Principle VII](../constitution.md#vii-exploited-means-demonstrated) — every dilution destroys reviewer trust within one cycle.
2. **Your reviewers do not need it.** If your evaluation surface does not benefit from "demonstrated impact" as a discriminator (e.g., you only ever look at small targets where every true-positive is hand-validated anyway), the flag is still computed but plays no role in your reviewer workflow. That is acceptable.

What is **not** acceptable: relaxing the flag's setting criteria to make it fire more often. The flag's value is its rigor, not its frequency.

## Can the operator override a verdict?

Yes. From [`constitution.md` §Scope of authority](../constitution.md#scope-of-authority):

> This constitution constrains the **system's design**. It does not constrain the **operator's runtime decisions**: an operator may override any automated verdict, stop a run early, or disable a role. The system records the override; it does not refuse it.

The system records the override in the finding's history and surfaces it in audit views. It does not refuse the override.

## Why doesn't the spec prescribe specific severity weights or a specific yield threshold?

[FR-117](../spec.md#94-yield-auto-stop) is explicit: these are organization-specific judgments. The seed gives one example calibration (~3.15× per tier; 2× for `exploited`); your organization may calibrate differently. The *shape* (geometric, not linear) is the part the seed has an opinion about; the *numbers* are yours.

See [`docs/operations/budget-and-stop-conditions.md`](operations/budget-and-stop-conditions.md).

## How do I report a bug in this seed?

For a bug *in the seed itself* (an FR that contradicts another, a principle that is unenforceable, a section that is unclear): open an issue on this repo. See [`CONTRIBUTING.md`](../CONTRIBUTING.md).

For a security issue *in your Foundry-derived system*: follow your own organization's security process; this repo is not the upstream for your implementation.

For a security issue *in this repo or in a Cisco-operated Foundry-derived system*: see [`SECURITY.md`](../SECURITY.md).

## How do I propose changing a principle?

There is a procedure. See [`docs/governance/amendment-process.md`](governance/amendment-process.md). The short version: you must document the specific scenario in which the principle, as written, produces a worse outcome than violating it, with empirical evidence, *and* explain why the failure mode the principle was originally added to prevent does not apply in your scenario.

"It is inconvenient" is not grounds. Each principle was inconvenient.

## Where do I find a worked example of clarify → specify → done?

[`docs/worked-examples/example-clarification.md`](worked-examples/example-clarification.md) — fictional org "Acme Bank" walks through three rounds.

## What is "Project CodeGuard" exactly?

CodeGuard is an open detection-rule format; Cisco originated it and donated it to the [Coalition for Secure AI (CoSAI)](https://www.coalitionforsecureai.org/), where it is now maintained as an OASIS open project. The seed assumes a CodeGuard-shaped rule format, but does not require it; see "Do I need CodeGuard specifically?" above.

The flywheel diagram in [`docs/architecture/rule-gap-flywheel.md`](architecture/rule-gap-flywheel.md) illustrates how the seed contributes back to the corpus.

## Did I miss anything?

If you have a question not answered here, the canonical resources are:

1. [`README.md`](../README.md) — high-level adoption guide.
2. [`spec.md`](../spec.md) — system shape and FRs.
3. [`constitution.md`](../constitution.md) — principles.
4. [`docs/README.md`](README.md) — index of the rest of these docs.

If your question is not addressed in any of those, open an issue suggesting it for this FAQ.
