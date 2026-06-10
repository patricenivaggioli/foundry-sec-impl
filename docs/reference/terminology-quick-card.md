# Terminology Quick Card

**Audience:** anyone who wants the vocabulary of the seed without reading the full glossary first.

This is a condensed version. The full glossary lives at the **repo root** as [`GLOSSARY.md`](../../GLOSSARY.md), mirrored from [`spec.md` §2](../../spec.md#2-glossary). If this card disagrees with either, **the spec wins**.

## The picture

```
Operator ──► Orchestrator ──► Substrate ──► Roles (8 core, 5 extension)
                                  │
                                  ▼
                          Findings travel through:
                          candidate → triaged → confirmed → published
```

## Core nouns

| Term | One-line definition |
|---|---|
| **Target** | Software under evaluation. |
| **Testbed** | A running instance of the target that agents may probe. May be absent. |
| **Operator** | Human who configures, steers, and stops the evaluation. |
| **Agent** | LLM-backed worker with a defined role. |
| **Role** | Named specialization (Detector, Triager, etc.); one role can have many instances. |
| **Fleet** | All agent instances for one evaluation. |
| **Substrate** | Non-agent machinery: queue, finding store, sandbox, budget, dashboard. |
| **Index** | Structured representation of target source: symbols, call graph, embeddings. |
| **Sandbox** | Isolation boundary that constrains agent reach and writes. |

## Finding-related nouns

| Term | One-line definition |
|---|---|
| **Finding** | A claimed vulnerability at any lifecycle stage. |
| **Candidate** | A finding the Detector wrote; not yet investigated. |
| **Verdict** | The Triager's classification: `true-positive`, `false-positive`, `needs-review`, `not-applicable`, `code-quality`. |
| **Evidence gate** | The structural requirement a finding must satisfy to be `true-positive` ([spec §7.3](../../spec.md#73-evidence-gate)). |
| **Exploited** | `true-positive` whose headline impact was independently reproduced on the testbed. Set only by the Validator. |
| **Fingerprint** | Stable identifier (path + symbol + class). Excludes line numbers and snippets. |
| **Finding report** | Human-readable writeup the Reporter produces. |
| **Rule-gap** | Record that an exploratory true-positive was missed by every existing rule (FR-042). |

## Coordination & operations nouns

| Term | One-line definition |
|---|---|
| **Work queue** | Shared, ordered list of tasks agents claim from (atomic, mortal). |
| **Finding store** | Durable, fingerprint-indexed record of every finding. Internal, distinct from the issue tracker. |
| **Coverage log** | Append-only audit trail of (area × technique) pairs attempted. |
| **Budget governor** | Tracks spend, runtime, and trailing yield against operator caps. |
| **Coverage** | Degree to which evaluation goals were credibly attempted. |
| **Yield** | Severity-weighted confirmed findings per unit spend, over a trailing window. |
| **Claim** | Exclusive, crash-safe hold on a unit of work. |
| **Heartbeat** | Liveness signal an agent emits on its own execution lane. |

## Operator interaction nouns

| Term | One-line definition |
|---|---|
| **Evaluation goals** | Operator's written statement of what outcomes matter and what is in scope. |
| **Help request** | Operator-filed issue asking the fleet to do something specific. |
| **Operator message** | Agent-authored, async, one-way note to the operator (blocker / request / feedback / info). |
| **Steer** | Operator-delivered message to a specific agent or role, optionally interrupting. |

## Detector & rule corpus nouns

| Term | One-line definition |
|---|---|
| **Detection rule** | Reusable, versioned check for one vulnerability class. The rule corpus is an artifact independent of the agent code. |
| **Proof-of-concept (PoC)** | Self-contained, runnable artifact demonstrating a finding's headline impact. |
| **Security map** | Cartographer's output: architecture, attack surface, trust boundaries, data flow, threat model. |

## Things this card deliberately omits

- Full definitions with rationale — see [spec §2](../../spec.md#2-glossary).
- Variant terms used in different communities — see [`GLOSSARY.md`](../../GLOSSARY.md) for any synonyms.
- Implementation-specific terms ("our queue is a Postgres table") — those are clarification answers, not core terminology.

## See also

- [`../../GLOSSARY.md`](../../GLOSSARY.md) — full glossary at repo root.
- [`../../spec.md#2-glossary`](../../spec.md#2-glossary) — canonical glossary.
- [`fr-index.md`](fr-index.md) — FR list by section.
- [`principle-fr-matrix.md`](principle-fr-matrix.md) — principle × FR matrix.
