# Clarification Playbook

**Audience:** an operator running `/speckit.clarify` who needs guidance on what a good answer looks like.

The seed `spec.md` carries approximately three dozen `[NEEDS CLARIFICATION: ...]` markers, indexed in [`spec.md` §15](../../spec.md#15-open-questions-index). This playbook does **not** answer them for you — every answer is your organization's decision. It does:

- Group the markers by intent so you can answer related ones consistently.
- Flag known anti-answers — wording that reproduces production failures.
- Note where one answer cascades into new questions during `/speckit.specify`.

Where a marker has its own §15 entry, that entry is authoritative; this playbook is commentary.

## How to use this document

1. Open [`spec.md` §15](../../spec.md#15-open-questions-index) alongside this playbook.
2. Work the four groups in order: identity → integration → policy → extension.
3. For each marker, write the answer first, then check it against the anti-answers below.
4. Record any answer that "depends on a decision the team has not made" as a written follow-up. Do not paper over it.

## Group A: Identity & scope

These shape every later answer. Answer them first.

| Marker theme | Good answer looks like | Anti-answer (do not adopt) |
|---|---|---|
| **System name** | A specific name your organization owns. | "The system", "Foundry" (you do not own that name in your build). |
| **Authorized eval with source access** assumption ([§1.7](../../spec.md#17-assumptions)) | "Yes; we evaluate first-party services with full source." | "Sometimes" — that drives a different system; revisit before continuing. |
| **Merge / split / omit core roles** | A specific decision per role with a one-line rationale. | "We'll figure it out in plan." |

**Cascade:** if you split a role (e.g., split Detector into "rule-detector" and "exploratory-detector"), specify will author new FRs for each. Expect new markers in the next pass.

## Group B: Integration choices (spec.md §11)

The seed describes the *contract* each integration must satisfy. Your answer names the implementation.

### §11.1 Version control & issue tracker

- Good: "GitLab, with REST v4 and a service account `foundry-bot`."
- Anti: "Whatever the team uses." (The Reporter has to know which API to call.)
- Cascade: a self-hosted tracker likely surfaces a "what is the API endpoint and auth model" follow-up.

### §11.2 LLM provider

- Good: "Provider X via internal gateway Y; rate limits are exposed via response headers."
- Anti: "Multi-provider, we'll abstract over them." (Principle V — the provider is the rate arbiter — gets harder, not easier, behind an abstraction.)

### §11.3 Datastore

- Good: name the engine and the persistence model (e.g., "Postgres 16 with transactional writes for the finding store").
- Anti: "SQLite or Postgres depending on env." Pick one for the seed run.

### §11.4 Vector search

- Good: "Yes, we use [vendor]; [§5.2 FR-023](../../spec.md#52-indexer) similarity search is enabled."
- Good: "No vector store; FR-023 dropped per the marker."
- Anti: leaving the marker as TBD — it gates whether downstream roles even attempt similarity queries.

### §11.5 Deployment topology

- Good: "Single Kubernetes namespace, one StatefulSet per role, agents heartbeat via the substrate."
- Anti: "Distributed across our standard environments." Specific topology answers shape sandbox patterns ([`../operations/sandbox-patterns.md`](../operations/sandbox-patterns.md)).

### §11.6 Container / isolation runtime

- Good: a specific runtime that satisfies Principle IX (sandbox by infrastructure, not by prompt). Examples: gVisor, Firecracker microVMs, dedicated VMs per agent.
- Anti: "Standard Docker containers with a network policy." That is necessary but you must verify it actually blocks egress, not just *intends* to.

### §11.7 Authentication model

- Good: "OIDC with [IdP], scoped service accounts per role."
- Anti: "Shared credentials checked into the agent image." ([Project CodeGuard](https://github.com/cosai-oasis/project-codeguard) rule `codeguard-1-hardcoded-credentials`; CWE-798; presence-is-the-vulnerability per FR-087a.)

### §11.8 Agent harness

- Good: a specific harness (Claude Code, your in-house harness, etc.).
- Anti: "We'll write our own." If you do, the seed's role boundaries are still required; you are not exempted from FR-002, FR-005, FR-019.

### §11.9 Severity & classification schemes

- Good: name a scheme (CVSS v4, internal taxonomy, OWASP categories).
- Anti: "We'll use whatever the LLM emits." (Inconsistent severity is the operator's #1 complaint.)

### §11.10 Compliance mapping

- Good: explicit list ("PCI-DSS, SOC2") or explicit "none for the seed run".
- Anti: silence — the Reporter will guess.

### §11.11 Downstream export

- Good: "JSON to S3 nightly" or "issue tracker only".
- Anti: "TBD" — affects Reporter retention behavior.

### §11.12 Testbed

- Good: "Yes; isolated VM cluster reachable from the per-role egress allowlist (Validator required; Detector exploratory per FR-040; Triager may need access to satisfy FR-056 where configured)." Or: "No testbed; Validator records 'no testbed' per FR-066." (Principle VII: Exploited Means Demonstrated; without a testbed you cannot set `exploited`.)
- Anti: "Sometimes we run against production." That's not a testbed.

## Group C: Policy choices

| Marker theme | Good answer | Anti-answer |
|---|---|---|
| Severity scheme | Specific rubric, owned by the Reporter. | "We let the model choose." |
| Surface `needs-review` | Explicit yes/no per [§7.6](../../spec.md#76-label-taxonomy). | "Always — operator can filter." (Defeats Principle II.) |
| Label naming | Concrete strings (`triaged/true-positive`, etc.). | Free-form per agent. |
| Compliance mapping | A defined matrix or "none". | "Whatever maps cleanly." |

## Group D: Extension scope (spec.md §6)

The README is explicit: **say no to all five extension roles for your first build.**

If you must say yes, be honest about why:

| Extension | Adopt when… | Do not adopt when… |
|---|---|---|
| Deep-Tester (§6.1) | You have a stable testbed and findings routinely need POC binaries. | Your testbed does not yet exist. |
| Variant-Hunter (§6.2) | You have a vector store, semantic embeddings, and a confirmed true-positive corpus. | Any of those three is missing. |
| Attack-Mapper (§6.3) | Your reviewers are asking "could these chain?" and your evaluations are >2 quarters old. | First-build. |
| Remediator (§6.4) | You have a code-review process for AI-suggested changes; merge gating is mature. | You don't yet trust the Reporter's output. |
| Self-Improver (§6.5) | The rule corpus has measurable gaps with documented examples. | Day one. |

**Cascade:** every "yes" in §6 produces FRs with their own markers in the next specify pass. Budget for it.

## Anti-answers we have seen go wrong

These do not match any single marker; they appear *across* answers and reliably cause failures.

1. **"The model decides."** The model is not authoritative. Verdicts (Principle I), liveness (Principle III), and exploited (Principle VII) all require something the model cannot produce alone.
2. **"We'll harden it later."** The constitution principles are inviolable on day one, not on day ninety. A plan that defers them is in error per [`constitution.md` Precedence](../../constitution.md#precedence).
3. **"Internal rate caps are safer."** No. Principle V is explicit; below-provider caps mask the real signal.
4. **"We'll just timeout the agent if it's stuck."** No. Principle III; reclaim by heartbeat, never by clock.
5. **"Issue per detection."** No. Principle II; surface only what survives triage.

## When clarify reports "nothing outstanding"

Read `spec.md` end to end yourself. Look specifically for:

- Pronouns without antecedents.
- Phrases that read like template language ("the chosen X", "an appropriate Y").
- Sections renumbered but not rewritten.

If you find any, edit and re-run clarify. Tools assist; they do not certify.

## See also

- [`integration-decisions.md`](integration-decisions.md) — decision frameworks for §11 surfaces.
- [`extension-roles-when.md`](extension-roles-when.md) — when (if ever) to enable §6 extensions.
- [`../reference/open-questions-checklist.md`](../reference/open-questions-checklist.md) — printable companion to §15.
- [`../worked-examples/example-clarification.md`](../worked-examples/example-clarification.md) — fictional org walkthrough.
