# Quickstart: from seed to your first run

**Audience:** an operator who has just cloned the seed and wants their first end-to-end pass through spec-kit.

This document expands the README's [Getting started](../../README.md#getting-started) section. It does not replace it; if anything here disagrees with the README, the README wins.

## Prerequisites (concrete)

- A coding agent with spec-kit support (Claude Code, Cursor with spec-kit, or another compatible client).
- A target you are authorized to evaluate, with source access. (Per [`spec.md` §1.7](../../spec.md#17-assumptions), authorized eval with source access is an explicit assumption of the seed.)
- A frontier LLM endpoint and the credentials your spec-kit agent uses to reach it.
- A Git repository where your downstream implementation will live (separate from this seed clone).

## Step 0: read before you type

Before any commands, read:

1. [`../../README.md`](../../README.md) end to end.
2. [`../../constitution.md`](../../constitution.md) end to end. The constitution is short on purpose. Each principle's rationale paragraph is the case for *why* it cannot be relaxed.
3. [`../../spec.md`](../../spec.md) §1 (Purpose & Scope) and §4 (System Overview). You do not need to absorb the FR list yet.

If a principle in the constitution feels wrong for your situation, the most likely answer is "we have not hit that failure yet." Resist the urge to amend before you have implemented.

## Step 1: install spec-kit

Follow the [spec-kit installation instructions](https://github.com/github/spec-kit) for your coding agent. After installation you should have:

- A `.specify/` directory in your project root.
- The `/speckit.constitution`, `/speckit.specify`, `/speckit.clarify`, `/speckit.plan`, `/speckit.tasks`, `/speckit.implement`, `/speckit.analyze` commands.

Verify by running `/speckit.constitution` (with no arguments) — your agent should report no constitution is registered yet.

## Step 2: install the constitution

```sh
cp path/to/foundry/constitution.md  your-project/.specify/memory/constitution.md
```

Then run `/speckit.constitution` and tell the agent you are adopting an existing constitution. After this:

- `/speckit.plan` and `/speckit.analyze` will check derived artifacts against it.
- The 11 principles become non-negotiable for the rest of the workflow.

## Step 3: seed the specification

```sh
mkdir -p your-project/specs/001-foundry
cp path/to/foundry/spec.md  your-project/specs/001-foundry/spec.md
```

The seed `spec.md` ships with status `SEED` (see [`spec.md` header](../../spec.md)) and approximately three dozen `[NEEDS CLARIFICATION: ...]` markers indexed in [§15](../../spec.md#15-open-questions-index).

## Step 4: clarify

```
/speckit.clarify
```

The agent walks you through every marker. Answers fall into the four groups listed in the README ([Identity & scope](../../README.md#step-4-clarify), Integration choices, Policy choices, Extension scope).

### What a successful clarify looks like

- Identity & scope are answered in concrete sentences, not "the system" / "an LLM".
- Integration choices either name a specific product or explicitly say "to be picked during plan, with the constraints …".
- Every extension role is a deliberate yes or no — never "maybe".
- The agent appends a Clarifications log to your `spec.md` summarizing what was answered.

### What a failed clarify looks like

- Markers replaced with vague phrases that re-introduce ambiguity ("the chosen LLM", "an appropriate datastore").
- Extension roles silently turned on because their FRs sounded useful.
- A Clarifications log that does not match what your agent actually asked you.

If clarify reports nothing outstanding but a manual read still finds ambiguity, edit `spec.md` and re-run clarify. Tools assist; they do not certify.

See [`clarification-playbook.md`](clarification-playbook.md) for marker-by-marker guidance.

## Step 5: specify

```
/speckit.specify
```

Specify hardens the clarified seed: expands sections that your answers required, renumbers FRs contiguously, sets status from `SEED` to `DRAFT`, and runs the constitution conformance check.

Read the result. If anything reads as "someone else's system", clarify missed a question. Do **not** edit the spec to "fix" wording — re-clarify.

## Step 6: iterate

Specify routinely introduces new underspecification. The README warns about this in [Step 6](../../README.md#step-6-iterate-clarify-and-specify-until-they-converge); it is not a defect, it is the workflow.

Re-run `/speckit.clarify`. If markers exist, answer and re-run specify. Repeat. Two or three rounds is normal. One round is normal only if you said no to every extension role and your integration answers were already concrete.

Convergence criteria:

- `/speckit.clarify` reports nothing outstanding.
- A manual read of `spec.md` finds nothing that is not a decision *you* made.
- `/speckit.analyze` reports no constitutional conflicts.

## Step 7: plan, task, implement

```
/speckit.plan
/speckit.tasks
/speckit.implement
```

After milestones, run `/speckit.analyze` to detect drift between spec, plan, tasks, and code.

## What to expect on day one

- Clarify will surface decisions you have not formally made. That is its job.
- Specify will at least once expand a section in a way that requires another clarify pass. Expect this.
- The constitution will block at least one early plan choice. The blocker is doing its job. Read [`../principles/anti-patterns.md`](../principles/anti-patterns.md) before debating it.

## What to expect on day fourteen

- The Indexer and Cartographer are running and the Detector has produced its first findings.
- Almost none of those findings will be `true-positive`. That is by design (Principle II: Surface Only What Survives).
- The first signal of progress is the Triager rejecting candidates *with reasons your operator agrees with*, not the Detector firing more often.

## Pointers

- [`clarification-playbook.md`](clarification-playbook.md) — how to answer the markers in `spec.md` §15.
- [`integration-decisions.md`](integration-decisions.md) — decision frameworks for the §11 surfaces.
- [`extension-roles-when.md`](extension-roles-when.md) — when (if ever) to enable an extension role.
- [`../worked-examples/example-clarification.md`](../worked-examples/example-clarification.md) — fictional org walkthrough.
