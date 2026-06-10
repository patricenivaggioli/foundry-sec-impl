# Glossary

Standalone glossary of Foundry terminology, mirrored from [`spec.md` §2](spec.md#2-glossary). For readers who want only the vocabulary.

If this glossary disagrees with `spec.md`, **the spec wins**; this file is updated.

A condensed quick-card version (one row per term, fewer terms) is at [`docs/reference/terminology-quick-card.md`](docs/reference/terminology-quick-card.md).

| Term | Definition |
|---|---|
| **Target** | The software under evaluation: its source code, and optionally a running deployment of it (the *testbed*). |
| **Testbed** | A running instance of the target that agents may probe and exploit. May be absent. |
| **Operator** | The human who configures, starts, steers, and stops an evaluation. |
| **Evaluation goals** | The operator's written statement of what outcomes matter (e.g. "authentication bypass", "RCE on the control plane") and what is in scope to test. |
| **Agent** | An LLM-backed worker with a defined role, running in a loop, coordinating with peers via the shared substrate. |
| **Role** | A named agent specialization (Detector, Triager, etc.). One role may have many concurrent instances. |
| **Fleet** | All agent instances currently running for one evaluation. |
| **Finding** | A claimed vulnerability at any lifecycle stage, from "candidate" through "confirmed and reported". |
| **Candidate** | A finding that has been detected but not yet investigated. |
| **Verdict** | The Triager's classification of a candidate: `true-positive`, `false-positive`, `needs-review`, `not-applicable`, or `code-quality`. |
| **Evidence gate** | The structural requirement a finding must satisfy before it may be classified `true-positive`. See [`spec.md` §7.3](spec.md#73-evidence-gate). |
| **Exploited** | A `true-positive` finding whose headline impact has been independently reproduced against the testbed by a clean-room check. See [`spec.md` §7.4](spec.md#74-exploited). |
| **Fingerprint** | A stable identifier for a finding, used for deduplication across runs. See [`spec.md` §7.5](spec.md#75-fingerprint). |
| **Finding report** | The human-readable writeup of a confirmed finding: description, impact, reproduction, severity, classification. |
| **Security map** | The Cartographer's output: architecture overview, attack-surface enumeration, trust-boundary map, data-flow description, threat model. |
| **Detection rule** | A reusable, versioned check for one vulnerability class, applied by the Detector to each function in scope. The rule corpus is an artifact independent of the agent code. |
| **Rule-gap** | A record that an exploratory finding was confirmed `true-positive` and no detection rule would have produced it; the input to growing the rule corpus. See FR-042. |
| **Coverage** | The degree to which the evaluation goals have been credibly attempted. |
| **Yield** | Severity-weighted confirmed findings per unit of spend, measured over a trailing window. |
| **Work queue** | The shared, ordered list of tasks agents claim from. See [`spec.md` §8](spec.md#8-coordination-substrate). |
| **Finding store** | The durable, fingerprint-indexed record of every finding at every lifecycle stage; internal, queryable by every role. Distinct from the issue tracker. |
| **Coverage log** | The append-only record of which (area × technique) pairs the fleet has attempted; an audit trail, not a stop-list. See FR-046. |
| **Budget governor** | The substrate component that tracks spend, runtime, and trailing yield against operator caps and signals the Orchestrator to halt. See [`spec.md` §9.3–§9.4](spec.md#93-budget). |
| **Help request** | An operator-filed issue asking the fleet to perform a specific action; resolved by the Orchestrator's conversational facet. See FR-015. |
| **Operator message** | An agent-authored, asynchronous, one-way note to the operator (blocker, request, feedback, or informational), deduplicated across the fleet. The agent→operator counterpart of a help request. See FR-102a. |
| **Proof-of-concept (PoC)** | A self-contained, runnable artifact that demonstrates a finding's headline impact against the testbed. See FR-063. |
| **Claim** | An agent's exclusive, crash-safe hold on a unit of work (a task, a finding, a target file). |
| **Substrate** | The non-agent machinery every role depends on: work queue, finding store, sandbox, budget tracker, dashboard. |
| **Index** | The structured representation of the target's source: symbols, call graph, cross-references, embeddings. |
| **Sandbox** | The isolation boundary around the agent fleet that constrains what it can reach and modify. |

## See also

- [`spec.md` §2](spec.md#2-glossary) — canonical glossary; this file is a mirror.
- [`docs/reference/terminology-quick-card.md`](docs/reference/terminology-quick-card.md) — condensed quick-card.
- [`README.md`](README.md) — adoption guide.
