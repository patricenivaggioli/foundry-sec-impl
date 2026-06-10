# Role Interactions

**Audience:** a platform engineer or reviewer who wants to see how the eight core roles cooperate across a finding's lifetime, in one diagram per flow.

The spec describes each role section by section ([`spec.md` §5](../../spec.md#5-core-agent-roles)). This page presents the **cross-role views**: the same information, viewed as flows. Every flow cites the FRs it depicts; none invents new requirements.

## 1. Detection → Triage → Validation → Report

The primary finding pipeline.

```mermaid
sequenceDiagram
    participant Detector
    participant FindingStore as Finding Store (substrate)
    participant Triager
    participant Validator
    participant Reporter
    participant IssueTracker as Issue Tracker

    Detector->>FindingStore: write candidate (FR-043, FR-044)
    Note over Detector,FindingStore: Dedup by fingerprint (FR-045, FR-090)

    Triager->>FindingStore: claim candidate (atomic, Principle IV)
    Triager->>Triager: investigate per §5.5 procedure
    Triager->>Triager: apply evidence gate (FR-052, §7.3)
    alt assigns true-positive or needs-review
        Triager->>FindingStore: write triaged finding<br/>verdict true-positive or needs-review
        Triager->>FindingStore: record rule-gap for true-positive if applicable (FR-042)
    else rejects
        Triager->>FindingStore: write rejected verdict (kept internal, Principle II)
    end

    Reporter->>FindingStore: claim true-positive report
    Reporter->>IssueTracker: write or update issue<br/>(keyed on fingerprint, FR-090, Principle VIII)

    Validator->>FindingStore: claim true-positive for reproduction
    Validator->>Validator: independent reproduction (FR-060, FR-061)
    alt headline impact observed
        Validator->>FindingStore: set exploited (FR-089)
    else no testbed or impact not observed
        Validator->>FindingStore: leave exploited unset (FR-062, FR-066)
    end
```

**Key invariants visible in the flow:**

- The Detector never writes to the issue tracker (FR-044).
- The Triager is the only role that promotes a finding to surfaceable status (FR-052, FR-057).
- The Validator owns independent reproduction and the `exploited` flag, not verdict promotion or demotion (FR-060, FR-061, FR-089).
- The Reporter keys on fingerprint, not line number (FR-090, Principle VIII), so cross-run inheritance and "update, do not recreate" both work.

## 2. Orchestrator heartbeat / reclaim

Liveness, atomic claim, mortal claims (Principles III and IV).

```mermaid
sequenceDiagram
    participant Agent
    participant Orchestrator
    participant Substrate

    loop while alive
        Agent->>Substrate: heartbeat (FR-100)
    end

    Orchestrator->>Substrate: read heartbeat ages (FR-005)

    alt heartbeat fresh
        Note over Orchestrator,Agent: leave the agent alone<br/>even if wall-clock runtime is long<br/>(Principle III)
    else heartbeat stale
        Orchestrator->>Substrate: release agent's claim(s) (FR-096)
        Orchestrator->>Agent: terminate
        Orchestrator->>Orchestrator: respawn with crash-loop backoff (FR-004, FR-007)
    end

    note over Orchestrator,Substrate: Session rotation (FR-118) is separate.<br/>It happens after claims are released or<br/>handed off, never as a liveness misfire.
```

**Why this is structured the way it is:**

- A wall-clock timeout cannot distinguish "hung" from "waiting on rate-limited upstream" (Principle III rationale).
- Reclaim is from the **substrate**, not from the agent process. The agent may already be a corpse; the substrate enforces that its claims do not outlive it (Principle IV).
- Session rotation (FR-118) is a deliberate cost-control rotation of a heartbeating agent's session *after* its current claim is settled. It is not a liveness signal.

## 3. Coverage-Guide feedback loop

Coverage-Before-Yield (Principle VI).

```mermaid
sequenceDiagram
    participant CoverageGuide
    participant Substrate
    participant Orchestrator

    loop while evaluation runs
        CoverageGuide->>Substrate: read detection output, scope, history
        CoverageGuide->>CoverageGuide: compute coverage map (§5.7)
        alt gaps exist
            CoverageGuide->>Substrate: queue directed task on work queue<br/>(FR-070)
        else no gaps
            CoverageGuide->>Substrate: set coverage-complete flag
        end
    end

    Orchestrator->>Substrate: read yield + coverage flag
    alt yield low AND coverage-complete
        Orchestrator->>Orchestrator: yield-gated auto-stop (§9.4)
    else yield low only
        Note over Orchestrator: do NOT auto-stop<br/>(Principle VI)
    end
```

**Why two conditions, not one:**

- Yield alone is noisy. It dips on hard targets early and recovers later. Auto-stopping on yield alone fires on the first dry spell.
- Coverage alone says nothing about progress on each uncovered cell.
- The conjunction "yield low AND coverage complete" is the honest "done" signal: we looked everywhere and the rate of new findings has flatlined.

## 4. Indexer + Cartographer gating

Why detection cannot start before the knowledge layer is ready.

```mermaid
sequenceDiagram
    participant Operator
    participant Orchestrator
    participant Indexer
    participant Cartographer
    participant Detector

    Operator->>Orchestrator: start evaluation
    Orchestrator->>Orchestrator: validate config (FR-001)
    Orchestrator->>Indexer: spawn

    Indexer->>Indexer: parse + call graph + query interface<br/>(FR-020, FR-021, FR-022)
    Indexer->>Orchestrator: signal queryable (FR-024)

    par
        Orchestrator->>Cartographer: spawn (after Indexer queryable)
    and
        Orchestrator->>Detector: spawn (FR-003)
    end

    Note over Cartographer,Detector: Detector consumes whatever<br/>Cartographer has produced so far<br/>(FR-036) — graceful degradation
```

**Visible from the diagram:**

- FR-003 forbids spawning non-Indexer roles before the Indexer is queryable. Skipping this gate produces detection candidates that cannot be triaged ("who calls this" is unanswerable).
- FR-036: roles consume whatever portion of the security map exists at the time they need it. They do not hard-fail when it is partial.

## 5. Operator interaction surface

Why conversational queries do not block lifecycle handling (FR-019).

```mermaid
sequenceDiagram
    participant Operator
    participant OrchestratorLifecycle as Orchestrator (lifecycle lane)
    participant OrchestratorChat as Orchestrator (conversational lane)
    participant Substrate

    par Lifecycle (deterministic, latency-sensitive)
        Operator->>OrchestratorLifecycle: status (FR-008)
        OrchestratorLifecycle-->>Operator: instant response
        OrchestratorLifecycle->>Substrate: respawn dead agent (FR-004)
    and Conversational (model-backed, latency-variable)
        Operator->>OrchestratorChat: free-form question (FR-013)
        OrchestratorChat->>Substrate: read records to ground answer
        OrchestratorChat-->>Operator: cited answer
    end

    Note over OrchestratorLifecycle,OrchestratorChat: Two lanes, one role.<br/>An LLM-backed answer never delays<br/>respawn or shutdown (FR-019).
```

## See also

- [`finding-lifecycle.md`](finding-lifecycle.md) — the state machine that the diagrams above traverse.
- [`substrate-contracts.md`](substrate-contracts.md) — the substrate interface every flow above depends on.
- [`rule-gap-flywheel.md`](rule-gap-flywheel.md) — how rule-gap recording (FR-042) closes the detection-to-prevention loop.
