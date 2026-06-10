# FR Index

**Audience:** anyone trying to find an FR by topic, role, or section without scrolling through `spec.md`.

This is a one-line index. The authoritative text for each FR lives in [`spec.md`](../../spec.md). If this index disagrees with the spec, the spec wins. Regenerate on every release.

Total: **143** FRs grouped by spec section.

## How to use this index

- The first column is the FR id. Lower-case suffixes (e.g. `FR-002a`) are amendments inserted between numbered FRs without renumbering.
- The second column is a one-line summary; consult the spec for the full text and rationale.
- Section headers link to the corresponding `spec.md` section.
- For *which principle does this FR enforce*, see [`principle-fr-matrix.md`](principle-fr-matrix.md).

## §5.1 Orchestrator

Spec link: [`spec.md` §5.1 Orchestrator](../../spec.md#51-orchestrator)

| FR | Summary |
|---|---|
| **FR-001** | The Orchestrator MUST validate the evaluation configuration before spawning any agent, refusing to start with a specific, actionable error if validation fails. (US-1) |
| **FR-002** | The Orchestrator MUST be the only component that spawns or terminates agent processes. |
| **FR-002a** | Agents MUST NOT spawn peer agents directly. |
| **FR-003** | The Orchestrator MUST gate the spawn of all non-Indexer roles on the Indexer reporting its knowledge base as queryable. |
| **FR-004** | The Orchestrator MUST maintain a configured count of each role and MUST respawn an agent that exits, subject to crash-loop backoff (FR-007). |
| **FR-005** | The Orchestrator MUST detect a **dead** agent by absence of heartbeat (see FR-100), not by wall-clock runtime. Wall-clock runtime MAY trigger session rotation per FR-118; it MUS... |
| **FR-006** | The Orchestrator MUST support a graceful drain: on shutdown signal, send each agent a wrap-up steer, wait a configurable grace period for natural exit, then terminate. |
| **FR-007** | The Orchestrator MUST apply exponential backoff when an agent exits within a short window of being spawned, with a cap on the per-attempt delay but no cap on attempts. |
| **FR-008** | The Orchestrator MUST expose a status query that reports, for each agent: role, instance index, alive/dead, current claim if any, last heartbeat age, restart count. (US-2) |
| **FR-009** | The Orchestrator MUST hot-reload changes to fleet composition (role counts) from configuration without a full restart, reconciling by spawning shortfall and gracefully draining... |
| **FR-010** | The Orchestrator SHOULD pre-flight check external dependencies (LLM provider reachable, issue tracker credentials valid, testbed reachable if configured) and report all failures... |
| **FR-011** | The Orchestrator MUST refuse to start a new evaluation run if a previous run hit a hard budget cap and the cap has not been raised, with a message stating which cap and how to r... |
| **FR-012** | The Orchestrator MUST NOT itself perform detection, triage, validation, or reporting. |
| **FR-013** | The Orchestrator MUST answer free-form operator questions about evaluation state, grounded in the actual substrate contents (not the model's general knowledge), citing the recor... |
| **FR-014** | The Orchestrator MUST accept operator-submitted tasks and place them on the work queue at the operator's chosen priority. (US-12) |
| **FR-015** | The Orchestrator MUST watch for operator help requests (issues the operator filed asking the fleet to do something specific) and resolve them: do what is asked, comment with wha... |
| **FR-016** | The Orchestrator MUST support steering a running agent: deliver an operator message to a specific agent or role, either at the agent's next idle point (non-disruptive) or immedi... |
| **FR-017** | The Orchestrator SHOULD support an interactive session in which the operator drives a single agent turn by turn with full tool access, for ad-hoc investigation. |
| **FR-018** | The Orchestrator's conversational facet MUST NOT modify verdicts, set `exploited`, or mark coverage complete on its own initiative. It may do so on explicit operator instruction... |
| **FR-019** | Conversational query handling MUST NOT share an execution lane with lifecycle handling: an in-flight LLM-backed answer MUST NOT delay agent respawn, heartbeat checking, status r... |

## §5.2 Indexer

Spec link: [`spec.md` §5.2 Indexer](../../spec.md#52-indexer)

| FR | Summary |
|---|---|
| **FR-020** | The Indexer MUST produce, for every source file in scope, an inventory of defined functions/methods with their location and body. The inventory MUST be produced by a determinist... |
| **FR-021** | The Indexer MUST produce a call graph (which function calls which) covering at minimum direct static calls. |
| **FR-021a** | The Indexer SHOULD resolve indirect and dynamic dispatch in the call graph where the target language permits it. |
| **FR-022** | The Indexer MUST expose its output through a query interface usable by other roles, supporting at minimum: get-function-body, get-callers, get-callees, find-symbol, full-text se... |
| **FR-023** | The Indexer SHOULD produce semantic embeddings of code units to support similarity search. |
| **FR-024** | The Indexer MUST signal "queryable" only when FR-020, FR-021, and FR-022 are satisfied. FR-023 MAY complete after the gate releases. |
| **FR-025** | The Indexer MUST persist its output such that a reader never observes a partially-written or deleted-but-not-yet-rewritten index (see FR-106a for the general atomic-persist rule). |
| **FR-026** | The Indexer MUST be incremental on re-run: only changed files are re-parsed; the call graph is patched, not rebuilt. |
| **FR-027** | The Indexer MUST respect a configured scope (include/exclude path patterns) and MUST NOT index outside it. |
| **FR-028** | The Indexer SHOULD degrade gracefully on files it cannot parse (log and skip; do not abort the run). |
| **FR-029** | Index construction MUST NOT block the Orchestrator's responsiveness. |

## §5.3 Cartographer

Spec link: [`spec.md` §5.3 Cartographer](../../spec.md#53-cartographer)

| FR | Summary |
|---|---|
| **FR-030** | The Cartographer MUST produce an **architecture overview**: the target's major components, their responsibilities, and how they communicate. |
| **FR-031** | The Cartographer MUST produce an **attack-surface enumeration**: every entry point reachable by an actor outside the target's trust boundary (network listeners, exposed APIs, CL... |
| **FR-032** | The Cartographer MUST produce a **trust-boundary map**: where in the target untrusted input becomes trusted, where one privilege level acts on behalf of another, and what valida... |
| **FR-033** | The Cartographer MUST produce a **data-flow description** for sensitive data classes (credentials, secrets, user data, control commands): where each enters, what it passes throu... |
| **FR-034** | The Cartographer MUST produce a **threat model** synthesizing FR-030 through FR-033: for each entry point and trust boundary, the attacker positions, attack goals, and threat ca... |
| **FR-035** | The Cartographer's outputs MUST be persisted where every other role can read them and SHOULD be summarizable into a digest small enough to include in another role's prompt context. |
| **FR-036** | Regardless of whether the Cartographer gates fleet spawn (see clarification below), other roles MUST function (at reduced quality) when the security map is absent or partial, an... |
| **FR-036a** | If any of FR-030–FR-034 fails to produce non-empty output, the Cartographer MUST write a minimal fallback for that section consisting of mechanically-derivable facts (file tree,... |

## §5.4 Detector

Spec link: [`spec.md` §5.4 Detector](../../spec.md#54-detector)

| FR | Summary |
|---|---|
| **FR-037** | The Detector MUST support **rule-based code analysis**: for each function in scope, apply each detection rule in the corpus as an LLM-evaluated check that asks whether the funct... |
| **FR-038** | The Detector MUST support **dependency scanning**: enumerate third-party dependencies and report those with known published vulnerabilities. |
| **FR-039** | The Detector MUST support **secret scanning**: report hardcoded credentials, keys, and tokens in the source tree. |
| **FR-040** | The Detector MUST support **exploratory hunting**: an agent instance with the goals, security map, testbed description (if any), and persistent notes in context, free to choose... |
| **FR-041** | The detection rule corpus MUST be a versioned artifact maintained independently of the Detector's agent code, such that rules can be added, revised, audited, and reused across e... |
| **FR-042** | When a finding produced by exploratory hunting (FR-040) is confirmed `true-positive` and no rule in the corpus would have produced an equivalent candidate, the Triager MUST reco... |
| **FR-043** | Each candidate finding MUST record at minimum: location (file, function), vulnerability class, a one-paragraph description of why the Detector believes it is a vulnerability, an... |
| **FR-044** | The Detector MUST write candidates to the finding store and MUST NOT create issue-tracker issues, send notifications, or otherwise surface candidates to humans. |
| **FR-045** | The Detector MUST deduplicate against existing findings by fingerprint (FR-090) before writing a candidate. |
| **FR-046** | Exploratory Detector instances (FR-040) MUST consult the coverage log before choosing an area and record what they swept, with what technique, when done. The coverage log is an... |
| **FR-047** | Exploratory Detector instances MUST NOT treat any prior agent's written claim of "fully covered", "saturated", or "no further work" as authoritative. |
| **FR-048** | The Detector MUST respect the configured scope (FR-027) and the operator's in-scope/out-of-scope rules (§9). |
| **FR-049** | The Detector SHOULD front-load each LLM detection call with the relevant context (function body, callers, callees, security-map excerpt) in the initial prompt rather than relyin... |

## §5.5 Triager

Spec link: [`spec.md` §5.5 Triager](../../spec.md#55-triager)

| FR | Summary |
|---|---|
| **FR-050** | The Triager MUST assign exactly one verdict from: `true-positive`, `false-positive`, `needs-review`, `not-applicable`, `code-quality`. Definitions in §7.2. |
| **FR-051** | The Triager MUST conduct an investigation before assigning a verdict, using at minimum: read the implicated code, trace the data flow from entry point to sink using the index, i... |
| **FR-052** | The Triager MUST NOT assign `true-positive` unless the **evidence gate** (§7.3) is satisfied (US-7): the investigation report cites specific code locations establishing (a) reac... |
| **FR-053** | A candidate that fails the evidence gate but that the Triager believes is likely real MUST be assigned `needs-review`, not `true-positive`. |
| **FR-054** | The Triager MUST record its full reasoning alongside the verdict. A verdict without an investigation report MUST be rejected by the finding store. |
| **FR-055** | The Triager MUST short-circuit candidates whose location is outside the configured scope to `not-applicable` without investigation. |
| **FR-056** | The Triager SHOULD consult the testbed during investigation when one is configured and the candidate's exploitability is uncertain from code alone. |
| **FR-057** | The Triager MUST surface a finding to humans (via Reporter) only on `true-positive`. Other verdicts are recorded in the finding store and visible via dashboard/Orchestrator but... |
| **FR-058** | The Triager SHOULD check whether a fingerprint-equivalent finding was already triaged in a related prior evaluation and, if so, inherit non-`true-positive` verdicts and use prio... |
| **FR-059** | The Triager MUST be idempotent: re-triaging a candidate replaces the prior verdict; it does not create a duplicate finding. |

## §5.6 Validator

Spec link: [`spec.md` §5.6 Validator](../../spec.md#56-validator)

| FR | Summary |
|---|---|
| **FR-060** | For every `true-positive` finding, where a testbed is configured, the Validator MUST attempt to reproduce the finding's stated impact against the testbed and MUST do so as an in... |
| **FR-061** | The Validator MUST set `exploited` only if the headline impact was directly observed on the live testbed. The following are NOT `exploited`: payload accepted but downstream effe... |
| **FR-062** | On reproduction failure, the Validator MUST record a structured explanation (what was attempted, what was observed, why it differs from the claim) and MUST NOT clear the `true-p... |
| **FR-063** | The Validator MUST produce a self-contained, runnable proof-of-concept artifact on success, with setup prerequisites documented in the artifact header. (US-10) The artifact demo... |
| **FR-064** | The Validator MUST operate within the sandbox (§9) and MUST honor the operator's hard rules (out-of-scope hosts, prohibited actions). A reproduction that would require violating... |
| **FR-065** | The Validator SHOULD limit reproduction attempts per finding (a small fixed number) before recording not-exploited. |
| **FR-066** | When no testbed is configured, the Validator MUST degrade to producing the PoC artifact without running it, MUST NOT set `exploited`, and MUST record "no testbed" as the reason. |

## §5.7 Coverage-Guide

Spec link: [`spec.md` §5.7 Coverage-Guide](../../spec.md#57-coverage-guide)

| FR | Summary |
|---|---|
| **FR-067** | The Coverage-Guide MUST, on first run, derive a finite checklist of (component × goal) coverage items from the evaluation goals and security map, where each item has a stated ba... |
| **FR-068** | The Coverage-Guide MUST NOT invent goals; if the evaluation goals document is empty or template placeholder text, it waits and re-checks rather than proceeding. |
| **FR-069** | The Coverage-Guide MUST, on each review cycle, gather evidence for each open checklist item from the coverage log, finding store, and work-queue history, and check off items whe... |
| **FR-070** | The Coverage-Guide MUST queue directed tasks on the work queue for checklist items with no matching activity, phrased so a Detector instance with no other context can act on them. |
| **FR-071** | The Coverage-Guide MUST set the coverage-complete flag only when every checklist item is closed, and MUST clear it if the operator changes the goals. |
| **FR-072** | The Coverage-Guide MUST NOT itself detect, triage, validate, or close work-queue tasks it queued. It reads, judges, and steers. |
| **FR-073** | The Coverage-Guide SHOULD record an estimate of remaining work each cycle, with a one-line basis, for the operator's planning. |
| **FR-074** | The Coverage-Guide MUST persist its checklist across restarts, atomically per FR-106a, without rebuilding it from scratch on each wake. |

## §5.8 Reporter

Spec link: [`spec.md` §5.8 Reporter](../../spec.md#58-reporter)

| FR | Summary |
|---|---|
| **FR-075** | For each `true-positive` finding, the Reporter MUST produce a self-contained report (US-10) including: title, affected component and location, description of the vulnerability,... |
| **FR-076** | The Reporter MUST assign each `true-positive` finding a weakness classification. [NEEDS CLARIFICATION: Which weakness taxonomy: CWE, an organization-internal taxonomy, or none?] |
| **FR-077** | The Reporter MUST assign each `true-positive` finding a severity. [NEEDS CLARIFICATION: Which severity scheme: CVSS (which version), a qualitative tier set (critical/high/medium... |
| **FR-078** | The Reporter MUST publish each finding report to the issue tracker as exactly one issue, with labels encoding at minimum: source (this system), verdict, severity, exploited yes/no. |
| **FR-079** | The Reporter MUST NOT publish a finding whose verdict is anything other than `true-positive` (subject to the FR-057 clarification). |
| **FR-080** | The Reporter MUST update, not duplicate, the issue for a finding whose report changes (severity revised, exploited flag set, evidence added). |
| **FR-081** | The Reporter MUST produce an evaluation-level rollup (US-9) containing at minimum: finding count by severity and by exploited status; findings grouped by owning component (per t... |
| **FR-082** | The rollup SHOULD identify keystone findings: those whose fix would break the most attack paths. This MAY depend on the Attack-Mapper extension (§6.3); without it, in-degree of... |
| **FR-083** | Finding reports MUST NOT name the LLM model or provider, the system's internal agent identifiers, or internal hostnames. |
| **FR-084** | Every code location referenced in a report MUST be a permalink that resolves for the report's reader. |

## §7.2 Verdicts

Spec link: [`spec.md` §7.2 Verdicts](../../spec.md#72-verdicts)

| FR | Summary |
|---|---|
| **FR-085** | Every finding MUST carry exactly one verdict once triaged. Verdicts are mutable (re-triage replaces). |
| **FR-086** | The finding store MUST retain `false-positive`, `not-applicable`, and `code-quality` findings with their reasoning. |

## §7.3 Evidence gate

Spec link: [`spec.md` §7.3 Evidence gate](../../spec.md#73-evidence-gate)

| FR | Summary |
|---|---|
| **FR-087** | A `true-positive` verdict MUST be accompanied by an investigation report containing at least one cited code location for each of: (a) **reachability**: an attacker-controlled en... |
| **FR-087a** | For vulnerability classes where **presence is the vulnerability** — a hard-coded credential, key, or token in source (CWE-798/259/321); use of a cryptographic primitive deprecat... |
| **FR-088** | Every cited code location in FR-087 MUST be mechanically verified to resolve to real code in the target at verdict time. A citation that does not resolve demotes the verdict to... |

## §7.4 Exploited

Spec link: [`spec.md` §7.4 Exploited](../../spec.md#74-exploited)

| FR | Summary |
|---|---|
| **FR-089** | `exploited` is a flag on a `true-positive` finding, set only by the Validator per FR-060 and FR-061, never by Detector, Triager, or Reporter, and never inferred. |

## §7.5 Fingerprint

Spec link: [`spec.md` §7.5 Fingerprint](../../spec.md#75-fingerprint)

| FR | Summary |
|---|---|
| **FR-090** | A finding's fingerprint MUST be a deterministic hash of (normalized file path, function/symbol name, vulnerability class). It MUST NOT include line numbers, code snippets, or de... |
| **FR-091** | Deduplication (FR-045, FR-058, FR-080) MUST key on fingerprint. |

## §7.6 Label taxonomy

Spec link: [`spec.md` §7.6 Label taxonomy](../../spec.md#76-label-taxonomy)

| FR | Summary |
|---|---|
| **FR-092** | Published findings MUST carry a minimal, fixed label set encoding: source-system marker, verdict, severity tier, exploited yes/no, weakness class. The system MUST create missing... |
| **FR-093** | The system SHOULD use one transient "in-progress" label that any role adds while holding a finding's claim and removes on release, layered over (not replacing) the verdict label. |

## §8.1 Work queue

Spec link: [`spec.md` §8.1 Work queue](../../spec.md#81-work-queue)

| FR | Summary |
|---|---|
| **FR-094** | The work queue MUST provide ordered tasks with at minimum: stable id, title, free-text description, priority position, state (`open` / `blocked` / `closed`). The substrate SHOUL... |
| **FR-095** | Claiming MUST be atomic: two agents claiming concurrently MUST receive different tasks (or one receives "none available"). |
| **FR-096** | A claim MUST be tied to the holder's liveness such that the claim is automatically released within bounded time of holder death, with no operator intervention. |
| **FR-097** | A task that has been claimed and released N times without completion (N small and operator-configurable) MUST auto-transition to `blocked`. |
| **FR-098** | The queue MUST be operator- and agent-writable (add, edit, reprioritize, close) at runtime. |
| **FR-098a** | An agent that discovers follow-on work outside the scope of its current claim SHOULD queue it as a new task rather than pursue it inline or steer a peer toward it (FR-102). An a... |
| **FR-099** | Task ids MUST be stable and distinct from priority positions. |

## §8.2 Liveness

Spec link: [`spec.md` §8.2 Liveness](../../spec.md#82-liveness)

| FR | Summary |
|---|---|
| **FR-100** | Every agent MUST emit a heartbeat at a fixed short interval to a location the Orchestrator and the claim mechanism observe. Liveness is defined as "heartbeat age below threshold... |
| **FR-101** | Heartbeat emission MUST NOT be blocked by the agent's primary work. |

## §8.3 Inter-agent communication

Spec link: [`spec.md` §8.3 Inter-agent communication](../../spec.md#83-inter-agent-communication)

| FR | Summary |
|---|---|
| **FR-102** | Agents MAY send messages to peers. A peer message MUST be delivered as advisory, prefixed to distinguish it from operator instruction, and the recipient MUST treat it as a hint,... |
| **FR-102a** | Agents MUST be able to post an asynchronous **operator message**: a short, one-way note surfaced to the operator, tagged with the originating agent and a kind drawn from at mini... |
| **FR-102b** | Operator messages MUST be deduplicated across the fleet before surfacing: when a new message is substantively equivalent to a recent unacknowledged one, it is suppressed and the... |
| **FR-102c** | The operator MUST be able to acknowledge an operator message (removing it from the unacked view and from the dedup pool) and SHOULD be able to reply, where a reply is delivered... |
| **FR-102d** | Agents MUST NOT use operator messages for progress narration, finding-specific details, or questions the agent can answer from the substrate. |
| **FR-103** | Agents SHOULD NOT use peer messages for status updates or work delegation; the work queue (FR-098, FR-098a) and claim state already encode those. |

## §8.4 Shared notes

Spec link: [`spec.md` §8.4 Shared notes](../../spec.md#84-shared-notes)

| FR | Summary |
|---|---|
| **FR-104** | The fleet MAY maintain a shared persistent-notes document that fresh agent instances read at startup, containing high-value cross-cutting facts (credentials, environment gotchas... |
| **FR-104a** | Where a shared-notes document exists, it MUST be size-bounded and lock-protected for writes. |
| **FR-104b** | The shared-notes document MUST NOT contain coverage claims, finding-specific details, or "X is done" assertions. |

## §8.5 Rate governance

Spec link: [`spec.md` §8.5 Rate governance](../../spec.md#85-rate-governance)

| FR | Summary |
|---|---|
| **FR-105** | The system MUST NOT impose internal rate caps below the upstream provider's actual limit. The provider is the rate arbiter; the system's job is to handle the provider's backpres... |
| **FR-106** | Backoff on provider rate-limit MUST be shared across all agents calling that provider, not per-agent. |

## §8.6 Atomic persistence

Spec link: [`spec.md` §8.6 Atomic persistence](../../spec.md#86-atomic-persistence)

| FR | Summary |
|---|---|
| **FR-106a** | Every persisted artifact that more than one component reads — the index, the finding store, the coverage checklist, the shared-notes document — MUST be updated by writing the ne... |

## §9.1 Sandbox

Spec link: [`spec.md` §9.1 Sandbox](../../spec.md#91-sandbox)

| FR | Summary |
|---|---|
| **FR-107** | The agent fleet MUST run inside an isolation boundary (US-6) that constrains network egress to an operator-configured allowlist (the LLM provider, the issue tracker, the testbed... |
| **FR-108** | The sandbox MUST mount the target source, the agent configuration, the agent prompts, and the sandbox's own definition as read-only to the agents. |
| **FR-109** | The operator MUST be informed at setup time that allowlisted destinations are pivot points: an agent that can reach the testbed can reach whatever the testbed can reach; an agen... |

## §9.2 Scope rules

Spec link: [`spec.md` §9.2 Scope rules](../../spec.md#92-scope-rules)

| FR | Summary |
|---|---|
| **FR-110** | The configuration MUST support an operator-authored hard-rules block, delivered to every agent in its system prompt, stating in plain language what the agent must never do (out-... |
| **FR-111** | When operating against any system that is not a disposable testbed, the default hard rules MUST prohibit at minimum: denial of service, data deletion or modification, credential... |

## §9.3 Budget

Spec link: [`spec.md` §9.3 Budget](../../spec.md#93-budget)

| FR | Summary |
|---|---|
| **FR-112** | The Orchestrator MUST track cumulative LLM spend (in currency) and cumulative wall-clock runtime across all runs of an evaluation, halting the fleet when either exceeds an opera... |
| **FR-113** | Spend tracking MUST account for every model call by every role. Where the provider does not report cost directly, the system MUST estimate from token counts and configured rates... |
| **FR-114** | Budget caps default to unset (unlimited). The pre-flight check (FR-010) SHOULD warn when both are unset. |

## §9.4 Yield auto-stop

Spec link: [`spec.md` §9.4 Yield auto-stop](../../spec.md#94-yield-auto-stop)

| FR | Summary |
|---|---|
| **FR-115** | The system MUST compute trailing yield: confirmed findings, weighted by severity and by `exploited` status, divided by spend, over a trailing spend window. |
| **FR-116** | The Orchestrator MUST halt the fleet when trailing yield falls below an operator-set threshold (US-4), but ONLY when all of: (a) at least one full trailing window of spend has a... |
| **FR-117** | Severity weights, the exploited multiplier, the trailing window size, the minimum runtime, and the threshold MUST be operator-configurable. The seed does not prescribe values. |

## §9.5 Agent lifecycle limits

Spec link: [`spec.md` §9.5 Agent lifecycle limits](../../spec.md#95-agent-lifecycle-limits)

| FR | Summary |
|---|---|
| **FR-118** | Each role's instances SHOULD have a configurable soft session limit after which the agent is steered to wrap up and release its claims, and a hard limit after which the Orchestr... |
| **FR-119** | An agent that has genuinely run out of useful work MAY retire itself; the Orchestrator spawns a fresh instance in the slot. |
| **FR-119a** | Agents MUST NOT invent busywork to avoid retirement. |

## §10. Observability

Spec link: [`spec.md` §10. Observability](../../spec.md#10-observability)

| FR | Summary |
|---|---|
| **FR-120** | The system MUST provide an operator dashboard (US-2) showing at minimum: per-agent state (role, index, alive, current claim, heartbeat age); finding counts by verdict, severity,... |
| **FR-121** | The system MUST provide a merged live activity feed across all agents, filterable by role and by event kind. |
| **FR-122** | The system MUST log every agent session in a structured, replayable format (turns, tool calls, tool results, token usage) to durable storage. |
| **FR-123** | The system SHOULD provide a per-role cost and token rollup, and a tool-usage histogram, sufficient for an operator (or the Self-Improver extension) to identify where spend is go... |
| **FR-124** | The status query (FR-008) and dashboard MUST agree with each other and with the substrate's actual contents. |
| **FR-125** | The system MUST surface its own degraded states (provider unreachable, index incomplete, sandbox misconfigured, abnormal error rate) on the dashboard prominently, not only in logs. |

## §12. Configuration Model

Spec link: [`spec.md` §12. Configuration Model](../../spec.md#12-configuration-model)

| FR | Summary |
|---|---|
| **FR-126** | The configuration MUST be a single document (or a single directory treated as one) under version control alongside the evaluation's outputs. |
| **FR-127** | Secrets (API keys, tokens, testbed credentials) MUST NOT be stored in the configuration document. The configuration references them; a separate non-version-controlled mechanism... |
| **FR-128** | The Orchestrator MUST hot-reload `budget` and `rules` changes at runtime, in addition to the `fleet` hot-reload required by FR-009. |
| **FR-128a** | Changes to `target`, `sandbox`, and `integrations` MAY require a restart. |
| **FR-129** | A configuration with unfilled required fields MUST fail FR-001 validation with a message naming each missing field. |

## Regenerating this index

This index is mechanically extracted from `spec.md` at the time of writing. If the spec changes, regenerate:

- Iterate over each line of `spec.md`.
- Track the most recent `## ` (h2) and `### ` (h3) header.
- For each line matching `^- \*\*(FR-\d+[a-z]?)\*\*: (.*)`, emit `(fr, section, body)`.
- Strip the trailing `*Rationale: ...*` from each body.
- Group by section; render as the tables above.

The companion [`principle-fr-matrix.md`](principle-fr-matrix.md) is also regenerated at each MINOR-or-greater release per [`constitution.md` §Compliance review](../../constitution.md#compliance-review).
