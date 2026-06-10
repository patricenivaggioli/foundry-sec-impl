# Foundry Security Spec

**An open specification for agentic AI security evaluation, from Cisco.**

[![Status](https://img.shields.io/badge/Status-Seed_v0.1.0-orange.svg)](CHANGELOG.md)

Cisco's Advanced Security Initiatives Group has built and operated an agentic security evaluation internally across several iterations and deployment models, and along the way accumulated a long list of design decisions that turned out to matter and a longer list that turned out not to.

**Foundry distills that experience into a single, organization-neutral specification.** It is the design that, across those iterations, consistently proved most effective. It is not our code. It is the shape of a system that works, with every lesson we learned written down as a requirement and every place where the right answer depends on *your* infrastructure left as an explicit open question.

You bring a frontier LLM and a target to evaluate. Foundry gives you the architecture, the invariants, and the guardrails. You build your own implementation, on your own stack, using the specification as the blueprint.

## What's in this repository

| File | Purpose |
|---|---|
| [`spec.md`](spec.md) | The seed specification. Eight core agent roles, five extension roles, the finding lifecycle, the coordination substrate, governance and safety requirements, and ~130 functional requirements with inline rationale explaining *why* each one exists. Deliberately underspecified at every organization-specific decision point; those points are marked `[NEEDS CLARIFICATION: ...]` for you to resolve. |
| [`constitution.md`](constitution.md) | Eleven inviolable principles that any implementation must uphold regardless of stack. Each one encodes a production failure we shipped, diagnosed, and fixed. These constrain every plan and task derived from the spec. |
| [`GLOSSARY.md`](GLOSSARY.md) | Standalone glossary of Foundry terminology, mirrored from [`spec.md` §2](spec.md#2-glossary). For readers who want only the vocabulary. |
| This README | How to turn the seed into your own system. |

There is **no code** in this repository, and that is intentional. The specification is the deliverable.

### Companion: CodeGuard

Foundry's Detector role ([§5.4](spec.md#54-detector)) runs on a corpus of LLM-evaluated detection rules. The rule format we use is **[CodeGuard](https://project-codeguard.org)**, which Cisco open-sourced well before Foundry existed and donated to the [Coalition for Secure AI (CoSAI)](https://www.coalitionforsecureai.org/), where it is now maintained as an OASIS open project. Foundry did not invent CodeGuard; Foundry was designed to *consume* it, and to contribute back the one thing a static rule corpus cannot do for itself: grow from operational experience.

That contribution is the **detection-to-prevention flywheel** at the center of Foundry's design:

1. **Rules sweep** every function in the target. Systematic, repeatable, finds what you already knew to look for.
2. **Exploratory agents hunt** alongside. Creative, target-specific, finds what no rule describes yet.
3. When exploration confirms something the rules missed, Foundry **records a rule gap**.
4. The gap is **generalized into a rule** (a new one, or a revision of one that should have fired). The rule lands in the corpus.
5. The next sweep, on this target and every future target, **catches that whole class on the first pass**. Exploration is freed to hunt further out.
6. Repeat. There is no terminal state; every evaluation enlarges the corpus.

And because CodeGuard rules are portable, the same corpus loads into an LLM coding assistant as its secure-coding rule set: the bug class your last evaluation taught the corpus to *detect* is now *prevented* at the keystroke, in every developer's editor, before the next evaluation ever runs. **Every turn of the loop improves detection here and prevention everywhere.**

CodeGuard stands on its own and predates this work; you can run Foundry with a different rule format. What Foundry adds is the machinery that turns a rule corpus from a maintained artifact into a self-improving one.

## Why we're releasing a spec instead of a tool

Our internal systems are tightly coupled to Cisco's infrastructure: our cloud provider, our issue tracker, our LLM gateway, our deployment platform, our severity taxonomy. Open-sourcing that code would give you something that runs in exactly one environment: ours.

What transfers is the *design*: which agent roles you need and why, what each must guarantee, how findings flow from detection to publication, what "done" means for an evaluation, where the quality gates go, and which shortcuts will hurt you six months in. That design is infrastructure-neutral, and it is what this repository contains.

The specification is written to be consumed by [spec-kit](https://github.com/github/spec-kit) (or any spec-driven development workflow): you run it through a clarification step that resolves the open questions against your environment, and out the other side comes *your* spec, for *your* implementation, on *your* stack.

## Who this is for

- **Security teams** with access to a frontier LLM, software they need to evaluate, and the question "how do we turn this model into a system that produces findings we can trust?"
- **Platform and tooling teams** building internal security-evaluation capabilities who would rather start from a proven shape than a blank page.
- **Researchers** studying AI-assisted vulnerability discovery who want a reference architecture grounded in production operation rather than benchmarks.

This is **not** a turnkey scanner. If you want something you can `pip install` and point at a repo today, this is not that. If you want to build the thing that your organization will still be running in three years, this is the blueprint.

---

## Getting started

### Prerequisites

- A coding agent that supports the [spec-kit](https://github.com/github/spec-kit) workflow (Claude Code or compatible).
- A repository where your implementation will live.
- Rough answers to: which LLM provider, which issue tracker, which datastore, where it will run. You don't need these finalized; the clarify step will walk you through them.

### Step 0: Read the constitution

Open [`constitution.md`](constitution.md) and read it end to end. It is short. Each principle has a "why this is inviolable" paragraph describing the production failure that motivated it. If any principle seems wrong for your situation, the answer is more often "we have not hit that failure yet" than "that failure cannot happen here."

### Step 1: Install spec-kit in your project

Follow the [spec-kit installation instructions](https://github.com/github/spec-kit) for your coding agent. At the end you should have a `.specify/` directory in your project root and the `/speckit.*` commands available in your agent.

### Step 2: Install the constitution

```sh
cp path/to/foundry/constitution.md  your-project/.specify/memory/constitution.md
```

Then run `/speckit.constitution` and indicate you are adopting an existing constitution. The agent will register it as the authority that later steps check against.

### Step 3: Seed the specification

```sh
mkdir -p your-project/specs/001-foundry
cp path/to/foundry/spec.md  your-project/specs/001-foundry/spec.md
```

### Step 4: Clarify

```
/speckit.clarify
```

This is the step the seed was written for. The agent reads `spec.md`, finds every `[NEEDS CLARIFICATION: ...]` marker (around three dozen; [§15 of the spec](spec.md#15-open-questions-index) indexes them all), and walks you through them as questions. They fall into four groups:

| Group | Examples | Guidance |
|---|---|---|
| **Identity & scope** | System name; does "authorized eval with source access" hold; merge/split/omit any of the eight core roles | Answer these first; they shape everything after. |
| **Integration choices** | VCS, issue tracker, LLM provider, datastore, deployment target, isolation runtime, agent harness, auth model | The seed describes the *interface contract* each must satisfy. "We use GitLab, one VM, Docker, SQLite" is a complete answer to half of these. |
| **Policy choices** | Severity scheme, weakness taxonomy, surface `needs-review`, label naming, compliance mapping | Use your organization's existing conventions where they exist. |
| **Extension scope** | Five yes/no questions for the optional roles | **Recommended: no to all five for your first build.** Get the eight core roles producing trustworthy findings, then revisit. |

**Tips:**
- "I do not know yet" is acceptable for integration and policy choices; the plan step will resurface them. It is not acceptable for identity and scope.
- When the seed says "the authors did X", that is one worked example, not a recommendation.
- When asked "merge, split, or omit", read the cost note at the end of that role's §5 section before answering.

At the end of clarify, your `spec.md` has been rewritten in place: markers replaced with your answers, dropped sections removed, a Clarifications log appended.

### Step 5: Specify

```
/speckit.specify
```

Hardens the clarified seed into a complete specification: expands sections your answers made necessary, renumbers FRs contiguously, verifies against the constitution, and sets status from `SEED` to `DRAFT`.

Read the result. This is now **your** specification. If anything in it reads as "someone else's system", clarify missed a question.

### Step 6: Iterate clarify and specify until they converge

**Specify can introduce new underspecification.** In particular:

- If you said *yes* to any extension role in §6, specify just authored FRs for it from a one-paragraph sketch. Those FRs will almost certainly carry their own `[NEEDS CLARIFICATION: ...]` markers (e.g., for Attack-Mapper: which graph store, what node-id scheme, how are by-design edges sourced).
- An integration choice you made can expose follow-on decisions (e.g., choosing a self-hosted issue tracker surfaces "what is the API endpoint and auth model" as a new question).

So after specify, run `/speckit.clarify` again. If it finds markers, answer them and re-run specify. Repeat until clarify reports nothing outstanding **and** a read-through of `spec.md` finds nothing that is not a decision you made. Two or three rounds is normal; one round is normal only if you said no to every extension and your integration answers were already concrete.

Do not proceed to plan with markers remaining. A `[NEEDS CLARIFICATION]` that survives into `/speckit.plan` becomes a guess baked into your design.

### Step 7: Plan, task, implement

```
/speckit.plan       # technical design satisfying the spec
/speckit.tasks      # ordered, dependency-aware build backlog
/speckit.implement  # work through it
```

After significant milestones, run `/speckit.analyze` to cross-check spec, plan, tasks, and code for drift.

---

## What the seed gives you, and what it does not

**Gives you:** the architecture (eight core roles, five extensions, substrate), the finding lifecycle (states, verdicts, evidence gate, fingerprinting), the coordination model (atomic claim, heartbeat liveness, auto-block), the governance model (sandbox, budget, yield-gated auto-stop, coverage gate), and the rationale behind every one of those.

**Does not give you:** detection rules, investigation prompts, severity rubrics, report templates, or any other *content*. Those are different for every organization and every target, and they are where most of your system's eventual quality will come from. Specifically, you will author:

- **The detection rule corpus** ([§5.4](spec.md#54-detector)). This is the artifact that compounds: every rule applies to every future evaluation, the rule-gap loop tells you which rules to write next, and the same corpus redeploys inside an LLM coding assistant as development-time prevention guardrails. [CodeGuard](https://github.com/cosai-oasis/project-codeguard) (see *Companion* above) is one concrete format that satisfies the spec's rule-corpus requirements; adopt it, fork it, or use it only as a reference for your own.
- **The Cartographer's document templates** ([§5.3](spec.md#53-cartographer)): how architecture, attack-surface, trust-boundary, data-flow, and threat-model documents are structured for your kind of target.
- **The Triager's investigation procedure** ([§5.5](spec.md#55-triager)).
- **The Reporter's writeup template and severity rubric** ([§5.8](spec.md#58-reporter)).
- **Your hard-rules block** ([§9.2](spec.md#92-scope-rules)) beyond the FR-111 minimum the seed already mandates.

The seed's value is that when you write a good detection rule, the system around it will not waste it: the finding will be deduplicated, evidence-gated, validated if possible, reported once, and counted toward done; and when exploration finds something your rules missed, the system will tell you which rule to write next.

---

## The architecture at a glance

```
                                   OPERATOR
                                      │
                       ┌──────────────▼──────────────┐
                       │        ORCHESTRATOR         │
                       │ lifecycle  +  conversational │
                       └──────────────┬──────────────┘
                                      │
                       ════════ SUBSTRATE ════════
                        work queue · finding store
                        sandbox · budget · dashboard
                       ════════════╤═══════════════
                                   │
   knowledge layer                 │   finding pipeline              oversight
 ┌───────┐┌─────────┐              │ ┌────────┐┌────────┐┌─────────┐┌────────┐┌─────────┐
 │INDEXER││ CARTO-  │──────────────┘ │DETECTOR││TRIAGER ││VALIDATOR││REPORTER││COVERAGE │
 │       ││ GRAPHER │                │        ││        ││         ││        ││ GUIDE   │
 └───────┘└─────────┘                └────────┘└────────┘└─────────┘└────────┘└─────────┘

         extension roles (build after core works):
         DEEP-TESTER · VARIANT-HUNTER · ATTACK-MAPPER · REMEDIATOR · SELF-IMPROVER
```

Eight core roles, each catching the previous role's failure mode. Read [§4 of the spec](spec.md#4-system-overview) for the full model and [§5](spec.md#5-core-agent-roles) for per-role requirements.


See [CHANGELOG.md](CHANGELOG.md).

## Contributing

Foundry is a specification, so contributions are amendments: a new lesson learned, a sharper requirement, a clarification axis we missed, a principle that turned out to be wrong. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

To report a security issue with this repository or with a Foundry-derived system operated by Cisco, see [SECURITY.md](SECURITY.md). To report a security issue with *your* Foundry-derived system, follow your own organization's process; we are not the upstream for your implementation.


## Provenance

Foundry is released by Cisco Systems, Inc. It distills the design of internal security-evaluation systems built and operated by Cisco's Advanced Security Initiatives Group. The specification is organization-neutral by design; Cisco's specific infrastructure choices appear only as worked examples in clarification questions, never as requirements.

## Acknowledgements
Original authors of the spec and constitution:
- Theo Morales (@kh0rvus)
- John Allbritten (@jallbrit) 


