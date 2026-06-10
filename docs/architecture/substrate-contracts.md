# Substrate Contracts

**Audience:** plan-step authors mapping [`spec.md` §8](../../spec.md#8-coordination-substrate) onto a real datastore, queue, and sandbox runtime.

The substrate is specified as **behavior**, not mechanism ([`spec.md` §8 preamble](../../spec.md#8-coordination-substrate)). Whether it is a database, a directory of files, or a message bus is a [§11.3 / §11.5](../../spec.md#11-integration-surfaces) decision. This page sketches the **interface contracts** every implementation must satisfy.

The pseudo-code below is illustrative. It is not a required API shape; it expresses the guarantees in code form so reviewers can check whether a candidate implementation honors them.

---

## Work queue contract (§8.1)

```text
queue.add(task) -> task_id                         # FR-094 (id stable, distinct from position)
queue.list(filters) -> [task]
queue.claim(agent_id) -> task | NONE_AVAILABLE     # FR-095 (atomic)
queue.release(claim, reason)                       # FR-096 (must be idempotent)
queue.complete(claim, result)
queue.update(task_id, edits)                       # FR-098, FR-098a
queue.reprioritize(task_id, new_position)
queue.transition(task_id, "blocked"|"open"|"closed")
queue.auto_block_after_n_releases(N)               # FR-097
```

### Required guarantees

| Guarantee | FR(s) | Principle |
|---|---|---|
| Two concurrent claims of the same task return different tasks (or "none available"). | FR-095 | IV |
| A claim is released within bounded time of the holder's heartbeat going stale, with no operator action. | FR-096 | III, IV |
| A task that has been claimed-and-released N times without completion auto-transitions to `blocked`. | FR-097 | — |
| Task ids are stable across position changes. | FR-099 | — |

### Anti-patterns

- **"The next agent breaks the lock if it looks stale."** Forbidden. Liveness-tied release is the only mechanism that produced neither stranded nor duplicate work in seed-author testing.
- **Operator-only unlock.** Forbidden. Crashes happen overnight; operators sleep.
- **Releasing on agent process exit alone.** Necessary but insufficient. The agent may be a corpse whose process supervisor is also wedged. Tie release to **heartbeat age** as the primary signal.

---

## Heartbeat / liveness contract (§8.2)

```text
agent.heartbeat() -> ack
substrate.heartbeat_age(agent_id) -> seconds
orchestrator.is_alive(agent_id) := (heartbeat_age(agent_id) < threshold)   # FR-100
```

### Required guarantees

| Guarantee | FR(s) | Principle |
|---|---|---|
| Heartbeat emission is on its own execution lane (not blocked by primary work). | FR-101 | III |
| Liveness is computed from heartbeat age, not wall-clock runtime. | FR-100 | III |
| Wall-clock runtime MAY trigger session rotation per FR-118; it MUST NOT trigger claim reclamation. | FR-005, FR-118 | III |

### Implementation notes

- A heartbeat that requires the same thread/event loop as the agent's primary loop reproduces the failure Principle III exists to prevent.
- The "heartbeat lane" is typically a separate goroutine, thread, or sidecar process emitting on a fixed short interval.
- The substrate's heartbeat read path MUST be cheap (the Orchestrator queries it in a tight loop) and MUST be authoritative (no caching with stale reads).

---

## Finding store contract (§7.1, §8.6)

```text
store.write(finding) -> finding_id                 # FR-043, FR-044
store.update_atomic(finding_id, edits)             # FR-106a
store.lookup_by_fingerprint(fp) -> finding | none  # FR-090, FR-091
store.list(filter) -> [finding]
store.transition(finding_id, new_verdict, reason)  # FR-085
```

### Required guarantees

| Guarantee | FR(s) | Principle |
|---|---|---|
| No reader observes a partially-written or deleted-but-not-yet-rewritten state. | FR-106a | XI |
| Findings are deduplicated by fingerprint at write time. | FR-045 | VIII |
| `false-positive`, `not-applicable`, `code-quality` findings are retained for re-run / future-query. | FR-086 | II |
| The Detector MUST NOT directly write to the issue tracker. | FR-044 | II |

### Atomic-persist patterns that satisfy FR-106a

- **Write new generation, then atomic rename** (POSIX rename, S3 conditional put-if-match).
- **Single-statement transaction** that commits the entire updated record.
- **Two-phase commit with idempotent replay** for distributed stores.

Patterns that **do not** satisfy FR-106a:

- Truncate then write.
- Delete record then insert replacement.
- Partial update across multiple keys without a transaction wrapping all of them.

---

## Sandbox contract (§9.1, Principle IX)

```text
sandbox.start(agent_image, allowlist) -> agent_handle
sandbox.kill(agent_handle)
sandbox.network_egress(handle, dest) -> blocked | allowed   # enforced by infra, NOT by prompt
sandbox.fs_write(handle, path) -> blocked | allowed         # enforced by infra
```

### Required guarantees

| Guarantee | FR(s) | Principle |
|---|---|---|
| An agent with full privileges *inside* the sandbox cannot reach a host outside the allowlist. | FR-107 | IX |
| Target source, agent configuration, prompts, and the sandbox's own definition are mounted read-only. | FR-108 | IX |
| The boundary is enforced by the runtime, not by the agent's prompt. | FR-107 | IX |

### Verification ritual

Before declaring a sandbox implementation acceptable, run, from inside the sandbox:

```text
curl https://attacker.example         # MUST be blocked
echo X >> /etc/hosts                  # MUST be denied
echo X >> /target/source/file.go      # MUST be denied (read-only)
curl https://allowlist.example        # MUST succeed
```

If any of the four behaves wrongly, the sandbox is misconfigured. Fix it before continuing.

---

## Inter-agent communication contract (§8.3)

```text
peer_message.send(from, to, body) -> ack            # FR-102 (advisory only)
operator_message.post(agent_id, kind, body) -> id   # FR-102a/b/c (deduplicated, async)
operator_message.acknowledge(id, by_operator)
operator_message.reply(id, body)                    # delivered as FR-016 steer
```

### Required guarantees

| Guarantee | FR(s) | Principle |
|---|---|---|
| Peer messages are advisory. The recipient treats them as hints, not commands. | FR-102 | X |
| Operator-message posting is non-blocking (no waiting for human). | FR-102a | — |
| Substantively-equivalent operator messages dedupe before reaching the operator. | FR-102b | — |
| Operator instructions outrank any agent's claim. | (whole spec) | X |

---

## Shared notes contract (§8.4)

The shared-notes document is a coordination primitive, not a source of truth. Agents read it as a hint about what peers have attempted; agents do **not** treat its claims as fact.

| Guarantee | FR(s) | Principle |
|---|---|---|
| Atomic update on write (FR-106a applies). | FR-106a | XI |
| Readable by every role with full content. | (§8.4) | — |
| Operator instructions outrank any note. | — | X |

---

## Rate governance contract (§8.5)

```text
provider_call(args) -> result
  # internal pre-throttle: NONE                     # FR-105
  # on 429 / quota error: shared backoff            # FR-106
```

### Required guarantees

| Guarantee | FR(s) | Principle |
|---|---|---|
| No internal rate caps below the provider's actual limit. | FR-105 | V |
| Backoff on rate-limit signals is shared fleet-wide, not per-agent. | FR-106 | V |

### Anti-patterns

- "Conservative cap of 80% of stated limit" — Forbidden. Caps below the real limit leave paid capacity idle and mask the real signal.
- Per-agent backoff state — N agents independently rediscover the same limit N times.

---

## Putting it together

A reasonable substrate implementation is:

- A SQL database with transactions for the work queue, finding store, and shared notes.
- A separate fast key/value lookup for heartbeats (Redis, sqlite WAL).
- An infrastructure-level network policy (gVisor, Firecracker, network policy + verified egress filter) for the sandbox.
- A shared in-memory backoff state, replicated across agent processes via the substrate.

A reasonable substrate implementation is **not**:

- A single shared filesystem with cooperative locking.
- A datastore where partial states are observable to readers.
- A network policy that "should be" enforced by the agent's good behavior.

## See also

- [`role-interactions.md`](role-interactions.md) — flows that traverse this contract.
- [`finding-lifecycle.md`](finding-lifecycle.md) — the state machine that the finding store hosts.
- [`../operations/sandbox-patterns.md`](../operations/sandbox-patterns.md) — three reference sandbox topologies.
- [`../principles/anti-patterns.md`](../principles/anti-patterns.md) — patterns each principle rejects.
