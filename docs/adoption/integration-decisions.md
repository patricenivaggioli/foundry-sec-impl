# Integration Decisions

**Audience:** an operator deciding which products satisfy each of the integration surfaces in [`spec.md` §11](../../spec.md#11-integration-surfaces).

The spec describes the **contract** each integration must satisfy. This document offers decision frameworks. It does **not** mandate any product. Where the seed itself is silent, that silence is intentional.

## Reading order

For each surface below:

1. Read the corresponding §11 subsection in the spec.
2. Read the constitution principle(s) that constrain it.
3. Apply the decision framework here.
4. Record your decision in `spec.md` (replacing the relevant marker).

## §11.1 Version control & issue tracker

Constraint: the Reporter (FR-075 — FR-084) writes to whatever issue tracker you pick. Cross-run inheritance keys on fingerprint (FR-090, Principle VIII).

| Decision criterion | Favors… | Avoid… |
|---|---|---|
| Can identify issues by stable external ID? | GitHub, GitLab, Jira, Linear. | Trackers without machine-readable IDs. |
| Supports comments and labels via API? | Most modern trackers. | Email-only workflows. |
| Webhooks for state changes? | If you want operator-help-request handling (FR-015). | If yes/no, configure poll fallback. |

**Anti-pattern:** running both a tracker and a parallel "issues spreadsheet". Pick one source of truth.

## §11.2 LLM provider

Constraint: Principle V — the provider is the rate arbiter. Internal pre-throttling below the provider's actual limit is prohibited.

Decision framework:

- **Single provider, official SDK** → simplest. Do this if you can.
- **Single provider, internal gateway** → fine, *if* the gateway forwards rate-limit signals (HTTP 429, retry-after, x-ratelimit-* headers) untouched.
- **Multi-provider, abstracted** → only if you can preserve per-provider backpressure. Naive load balancing across providers makes Principle V much harder.

Required capabilities the spec assumes:

- The provider's responses include rate-limit headers or equivalent backoff signals.
- Calls support timeouts at the call layer (separately from agent liveness).
- Token usage / cost is observable for budget enforcement (FR-112, FR-113).

## §11.3 Datastore

Constraint: Principle XI — persist atomically. The finding store must never be partially observable.

| Engine class | Notes |
|---|---|
| Postgres / MySQL with transactions | Easiest path; transactional updates make Principle XI cheap. |
| SQLite | Workable for single-host deployments; WAL mode required. |
| Document stores (Mongo, etc.) | Work, but transaction semantics across collections need explicit design. |
| Object stores (S3 etc.) | Acceptable for blobs, never for the live finding store unless you layer transactions on top. |

**Anti-pattern:** "delete old, write new" persistence flows. Always write new, then atomically rename or commit (see [`spec.md` §8.6](../../spec.md#86-atomic-persistence)).

## §11.4 Vector search

Constraint: optional per FR-023. If absent, the Indexer drops similarity search and the Variant-Hunter extension cannot be enabled (see [`extension-roles-when.md`](extension-roles-when.md)).

| Decision criterion | Favors enabling | Favors disabling |
|---|---|---|
| Have an existing embedding pipeline? | Enable. | Disable for first build. |
| Targets are heterogeneous (many languages, many components)? | Enable; similarity boosts triage. | Disable; rule-based detection is sufficient. |
| Operating at small scale (< 1M functions)? | SQLite + sqlite-vss may suffice. | Full vector DB is overkill. |

## §11.5 Deployment topology

Constraint: Principles III, IV, IX. Heartbeat-based liveness, atomic claim, infrastructure sandbox.

Three reference topologies (see [`../operations/sandbox-patterns.md`](../operations/sandbox-patterns.md) for details):

| Topology | When | Trade-off |
|---|---|---|
| Single-host containers | Dev, small targets, < 8 agents. | Sandbox boundary is the container; you must verify it actually holds. |
| Multi-host VMs | Medium scale; one VM per agent class. | Operationally heavier; isolation is real. |
| Cloud-isolated workers (Firecracker / gVisor / serverless containers) | Production scale. | Highest cost; strongest Principle IX guarantees. |

## §11.6 Container / isolation runtime

Constraint: Principle IX. The runtime, not the prompt, enforces network and filesystem boundaries.

Decision: pick a runtime that lets you specify, *and verify*, what an agent inside it can reach. Verify by attempting egress and write outside the allowlist as part of acceptance testing — if those succeed, the runtime is not the boundary.

Acceptable: gVisor, Firecracker, Kata Containers, hardened Docker with strict seccomp + network policies (verified), VM-per-agent.

Not acceptable as the sole boundary: prompt-level rules, agent self-restriction, "the agent will not call X because we told it not to".

## §11.7 Authentication model

Constraint: every credential the agent needs must come from the runtime, not the prompt or codebase ([Project CodeGuard](https://github.com/cosai-oasis/project-codeguard) rule `codeguard-1-hardcoded-credentials`; CWE-798; see the FR-087a presence-is-the-vulnerability carve-out).

| Pattern | Notes |
|---|---|
| Workload identity (OIDC, IRSA, GCP Workload Identity) | Preferred. No long-lived secrets. |
| Service accounts with short-lived tokens via secrets manager | Acceptable. Rotation must be automated. |
| Long-lived API keys mounted as env vars | Last resort. Document rotation procedure. |
| Hardcoded credentials | Forbidden. |

## §11.8 Agent harness

Constraint: roles are role-specific (Detector ≠ Triager) and the Orchestrator (FR-002) is the only spawner.

Existing harnesses that fit cleanly: Claude Code, Cursor agents, in-house wrappers around the LLM SDK that expose tools per role. The harness must support:

- Tool gating per role.
- A heartbeat mechanism that the Orchestrator observes (FR-005 / FR-100).
- Process or session boundaries the Orchestrator can terminate (FR-002).

## §11.9 Severity & classification schemes

Constraint: the Reporter's severity must be reproducible. The model is not the rubric.

Pick exactly one scheme. Examples:

- CVSS v4.0 with a documented enterprise vector profile.
- An internal taxonomy (Critical/High/Medium/Low/Informational) with explicit criteria.
- OWASP Top 10 categories for web targets.

Document the rubric in your Reporter's prompt template ([`spec.md` §5.8](../../spec.md#58-reporter)). The model applies the rubric; it does not invent it.

## §11.10 Compliance mapping

Decide before the first run whether findings are mapped to a compliance framework (PCI-DSS, SOC2, HIPAA, internal control catalog). "We'll add it later" usually never happens.

| Posture | Rationale |
|---|---|
| **Map from day one** | Adds maintenance, but reviewers can filter and roll up immediately. |
| **No mapping** | Acceptable for research / pre-prod systems. Document explicitly. |

## §11.11 Downstream export

Define exactly two things:

1. **Format** — JSON, SARIF, CSV, the issue tracker only, etc.
2. **Cadence and trigger** — on every triaged finding, nightly batch, on demand.

Anti-pattern: emitting findings to multiple downstream consumers with subtly different field shapes. Pick a canonical export format and adapt downstream.

## §11.12 Testbed

Constraint: Principle VII — `exploited` is set only by clean-room reproduction on a live testbed.

| Posture | Implication |
|---|---|
| **Live testbed available** | Validator can confirm impact; `exploited` flag is meaningful. |
| **No testbed** | Validator produces the PoC artifact without running it and records "no testbed" (FR-066). `exploited` cannot be set. Document the limitation in your spec. |
| **"We sometimes run against prod"** | Not a testbed. Forbidden by Principle IX practical reading and by basic operational safety. |

Testbed reachability is governed by the per-role egress allowlist (FR-107). The Validator requires it; the Detector's exploratory mode may use it where configured (FR-040), and the Triager may need access to satisfy FR-056 where configured. Only the Validator may set `exploited` (FR-089).

## Putting it together

Walk the surfaces top to bottom in clarify. Each answer should be:

- **Specific** (a product name or a concrete "no").
- **Constraint-aware** (cite the spec section and any constitutional principle).
- **Reversible** (record the answer in your spec; if you change later, treat as an amendment).

When in doubt, refer back to [`clarification-playbook.md`](clarification-playbook.md) for marker-by-marker guidance.
