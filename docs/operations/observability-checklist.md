# Observability Checklist

**Audience:** a platform engineer implementing the requirements in [`spec.md` §10](../../spec.md#10-observability) without prescribing a stack.

The spec describes **what** the dashboard and metrics must show; this checklist describes **how** to assemble those signals from common observability primitives. Pick a stack you already operate (Prometheus + Grafana, Datadog, OpenTelemetry + your sink of choice, an internal pipeline). The checklist is stack-agnostic.

If anything here disagrees with `spec.md` §10, the spec wins.

## Required signals (per FR-120)

The Operator dashboard MUST show, at minimum:

### Per-agent state

- [ ] Role.
- [ ] Instance index.
- [ ] Alive / dead status.
- [ ] Current claim (or "idle").
- [ ] Heartbeat age.
- [ ] Restart count.

**Source:** the substrate's heartbeat and claim tables. Counter and gauge metrics, plus a per-agent record table for the dashboard's tabular view. Update on heartbeat (every fixed short interval) and on claim/release events.

**Anti-pattern:** computing alive/dead status from process supervisor state alone. The substrate's heartbeat age is the source of truth ([Principle III](../../constitution.md#iii-liveness-by-heartbeat-never-by-clock)); the dashboard MUST reflect it.

### Finding counts

- [ ] By verdict (`true-positive`, `false-positive`, `needs-review`, `not-applicable`, `code-quality`).
- [ ] By severity tier.
- [ ] By exploited yes/no.

**Source:** the finding store. Count metrics, refreshed on writes that change verdict, severity, or `exploited` status. The dashboard should also show first-derivative (rate of change) so an operator can spot a stalled pipeline.

### Coverage checklist state

- [ ] Items attempted vs total.
- [ ] Coverage-complete flag (set / not set).

**Source:** the Coverage-Guide ([§5.7](../../spec.md#57-coverage-guide)).

### Budget against caps

- [ ] LLM spend consumed (USD or local equivalent).
- [ ] Wall-clock runtime consumed.
- [ ] Caps (configured value).

**Source:** the budget governor ([§9.3](../../spec.md#93-budget)).

### Trailing yield

- [ ] Yield value (severity-weighted findings per spend).
- [ ] Configured threshold.
- [ ] Coverage-complete flag (the conjunction prerequisite).

**Source:** [§9.4 / FR-115–FR-117](../../spec.md#94-yield-auto-stop). Display the threshold as a horizontal line on the yield chart so operators can see proximity.

### Work queue depth

- [ ] Open / blocked / closed counts.
- [ ] Per-named-queue (per FR-094 if you use multiple).

### Operator messages

- [ ] Unacknowledged operator messages by kind, with `blocker` visually distinguished ([FR-120](../../spec.md#10-observability), [FR-102a](../../spec.md#83-inter-agent-communication)).

## Activity feed (FR-121)

- [ ] Merged live activity feed across all agents.
- [ ] Filterable by role.
- [ ] Filterable by event kind (claim acquired, claim released, finding written, verdict assigned, message posted, etc.).

**Implementation patterns:**

- A structured-log topic per role; the feed UI is a multi-stream tail.
- An events table in the substrate; the feed reads with role/kind filters.

## Session logging (FR-122)

- [ ] Every agent session in structured, replayable format.
- [ ] Turns, tool calls, tool results, token usage.
- [ ] Durable storage (immutable; retention policy documented).

**Implementation patterns:**

- One log file per session, JSON-lines, written to S3 / GCS / object store at session end (or streamed via a write-ahead log if sessions are very long).
- Strict redaction of secrets and PII before write ([Project CodeGuard](https://github.com/cosai-oasis/project-codeguard) rule `codeguard-0-logging`).

## Cost & token rollups (FR-123)

- [ ] Per-role cost.
- [ ] Per-role token usage.
- [ ] Tool-usage histogram.
- [ ] Granularity sufficient for an operator (or Self-Improver) to identify where spend is going.

**Implementation patterns:**

- Tags / labels on every LLM call: `role`, `instance`, `tool`, `target`. Aggregate on the dashboard.
- Daily / weekly cost reports filed automatically into the operator's tracker if budget approaching cap.

## Dashboard / source-of-truth coherence (FR-124)

- [ ] The status query (FR-008) and the dashboard agree with each other and with the substrate's actual contents.

**This is the single most-important invariant in observability.** A dashboard that reads a stale or differently-computed view of the substrate produces operator decisions based on fiction.

**Implementation patterns:**

- Dashboard reads directly from the substrate, or uses only short-lived caches with reconciliation against the substrate.
- The status query and dashboard share a single read path / view so they cannot diverge.
- A periodic reconciliation job verifies that aggregate metrics match an authoritative recount; alerts on drift.

**Anti-pattern:** dashboard counts derived from a separate event stream that may be lossy.

## Degraded-state surfacing (FR-125)

The system MUST prominently surface its own degraded states on the dashboard:

- [ ] LLM provider unreachable.
- [ ] Index incomplete.
- [ ] Sandbox misconfigured.
- [ ] Abnormal error rate (per role, per provider, per tool).

**Implementation patterns:**

- A "system health" banner on the dashboard, color-coded.
- Independent health checks for each integration surface ([`spec.md` §11](../../spec.md#11-integration-surfaces)).
- A self-test suite that runs at startup and periodically thereafter, with failures bubbling to the banner.

**Anti-pattern:** burying these in logs only. Operators are looking at the dashboard; the dashboard must say something.

## Choosing a delivery mechanism (per the §10 marker)

The seed leaves dashboard *delivery* open ([§10 marker](../../spec.md#10-observability)). Common choices:

| Choice | When | Trade-off |
|---|---|---|
| Web UI served by the Orchestrator | First-build; small teams. | Lifecycle code now serves UI — keep it on a separate lane to satisfy [FR-019](../../spec.md#51-orchestrator). |
| Terminal UI | Constrained networks; audit-friendly. | No charts; no drill-down. |
| Static page regenerated on interval | Snapshot-style reporting. | Stale by definition; not suitable as the live dashboard. |
| Panels on existing observability stack (Grafana, Datadog) | Production. | Requires metric pipelines but reuses existing alerting/oncall. |

Make the choice explicit in the spec during clarify; it should not be a runtime configuration toggle.

## Verification

Before promoting an implementation past the seed run:

- [ ] Pull every signal listed above on the dashboard.
- [ ] Verify each value matches a manual query against the substrate.
- [ ] Verify the activity feed renders in real time and is filterable.
- [ ] Verify sessions are recorded and replayable.
- [ ] Verify a degraded state (e.g., kill the LLM provider connection in a test environment) surfaces on the dashboard.

If any item fails, observability is not yet adequate.

## Anti-patterns

- **"Logs only — operators tail with grep."** Loses every aggregate signal; operators stop looking at the system. Violates the spirit of FR-120.
- **"Dashboard built from stale cached metrics."** Drift from substrate is inevitable; FR-124 fails.
- **"Add observability later, after the system works."** Without observability, you cannot tell whether the system is working.
- **Logging secrets, tokens, or raw session IDs.** Forbidden ([Project CodeGuard](https://github.com/cosai-oasis/project-codeguard) rule `codeguard-0-logging`). Redact at emission, not at consumption.

## See also

- [`sandbox-patterns.md`](sandbox-patterns.md) — sandbox setup, including health checks for FR-125.
- [`budget-and-stop-conditions.md`](budget-and-stop-conditions.md) — yield/coverage stop logic that uses these signals.
- [`../architecture/role-interactions.md`](../architecture/role-interactions.md) — flows that produce these signals.
- [`../../spec.md#10-observability`](../../spec.md#10-observability) — canonical requirements.
