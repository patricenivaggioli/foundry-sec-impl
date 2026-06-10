<!--
SYNC IMPACT REPORT
═══════════════════════════════════════════════════════
Tasks version      : 0.1.0
Plan version       : 0.1.0
Spec version       : (current main)
Constitution       : 0.2.0
Status             : DRAFT — pre-`/speckit.analyze`
Coverage           : Phases P0–P5 (§7 of plan.md)
═══════════════════════════════════════════════════════
-->

# Foundry Sec — Implementation Tasks

| Field | Value |
|---|---|
| **Tasks version** | 0.1.0 |
| **Derived from** | `plan.md` 0.1.0 |
| **Decomposition** | One task ≈ one PR. Each task names its FR(s), constitution principle(s), and exit test. |
| **Conventions** | `[P0…P5]` phase tag · `(Sn)` story-points · `→ T-xxx` dependency · ⚠ blocks principle compliance |

## How to read this file

- Tasks are **claimable units of work**. The fingerprint of a task is `(phase, id)`; do not renumber.
- Every task lists: *Goal*, *Inputs*, *Outputs*, *Spec FRs*, *Constitution principles*, *Exit test*, *Dependencies*.
- A task is **done** when its exit test passes in CI on a clean checkout, not when "the code looks right".
- Tasks marked ⚠ block downstream work that depends on a constitutional invariant; do not ship around them.

---

## Phase P0 — Substrate (foundation)

**Phase exit:** one stub agent claims a task, heartbeats, and releases under a chaos test that kills it every 10 s, with no work loss and no double-claim.

### T-001 — Repository scaffolding *(S2)*

- **Goal:** Create the monorepo layout: `orchestrator/`, `agents/{indexer,cartographer,detector,triager,validator,coverage_guide,reporter}/`, `substrate/`, `harness/`, `proto/`, `migrations/`, `deploy/{compose,k8s}/`, `tests/`.
- **Outputs:** Empty packages with `pyproject.toml`, shared lint config (ruff, mypy strict), pre-commit hooks.
- **Exit test:** `make lint && make typecheck` green on empty modules.
- **Deps:** —

### T-002 — Postgres schema v1 *(S5)* ⚠

- **Goal:** Author migration `0001_substrate.sql` covering: `evaluations`, `agents`, `work_queue`, `findings`, `verdicts`, `evidence_citations`, `exploit_proofs`, `coverage_state`, `budget_state`, `overrides`, `session_logs`.
- **Spec FRs:** §7, §8, §9.3, FR-091, FR-095, FR-127.
- **Principles:** I, II, IV, VIII, XI.
- **Notes:**
  - `findings.fingerprint` = generated column from `(target_revision, path, symbol, vuln_class)`. **No line numbers, no snippet hashes.**
  - `work_queue.claim_expires_at TIMESTAMPTZ` driven by heartbeat (Principle III).
  - Row-level security policies keyed on `evaluation_id` for NFR-003.
  - `pgvector` and `pg_partman` extensions enabled.
- **Exit test:** Migration applies cleanly on Postgres 16; all RLS policies reject cross-evaluation reads in `tests/sql/test_rls.sql`.
- **Deps:** T-001

### T-003 — Insert-time citation resolver *(S5)* ⚠

- **Goal:** Implement `evidence_citations` BEFORE INSERT trigger that rejects citations whose `quoted_excerpt` is not a substring of the symbol's body in the indexed revision.
- **Principles:** I (this is where Principle I is enforced; do not relax this trigger).
- **Exit test:** `tests/sql/test_citation_gate.sql` — citation with bogus excerpt rejected; valid citation accepted; verdict `true-positive` with zero citations rejected.
- **Deps:** T-002

### T-004 — Atomic claim & heartbeat SQL *(S3)* ⚠

- **Goal:** Implement the `SELECT … FOR UPDATE SKIP LOCKED` claim CTE and `heartbeat()` function (extends `claim_expires_at`).
- **Spec FRs:** FR-005, FR-095, FR-096.
- **Principles:** III, IV.
- **Exit test:** `tests/sql/test_claims.sql` — 64 concurrent claimers get 64 distinct rows; killed claimer's row is reclaimable after TTL; live claimer's row is never reclaimed.
- **Deps:** T-002

### T-005 — gRPC proto definitions *(S2)*

- **Goal:** Author `proto/orchestrator.proto` and `proto/orchestrator_converse.proto` matching plan §4.1–4.2. Generate Python stubs.
- **Exit test:** Stubs compile; reflection endpoint lists both services.
- **Deps:** T-001

### T-006 — Orchestrator lifecycle lane skeleton *(S5)*

- **Goal:** asyncio service implementing `ValidateConfig`, `Up`, `Down`, `Status`, `HotReload`, `QueueTask`, `Steer`. NO LLM calls in this lane.
- **Spec FRs:** FR-001, FR-002, FR-002a, FR-006, FR-008, FR-009, FR-014, FR-016, FR-019, FR-128.
- **Principles:** III (heartbeat watcher).
- **Exit test:** `pytest tests/orchestrator/test_lifecycle.py` — `Up` spawns the configured fleet count; `Down` drains gracefully; `Status` reports per-agent heartbeat age.
- **Deps:** T-002, T-004, T-005

### T-007 — Conversational lane process pool *(S3)*

- **Goal:** Separate process group running `Ask`, `OpenInteractive`. Communicates with lifecycle lane only via Postgres `LISTEN/NOTIFY`.
- **Spec FRs:** FR-013, FR-017, FR-019.
- **Exit test:** `tests/orchestrator/test_lane_isolation.py` — a 30 s sleep injected into the conversational lane does not delay heartbeat checks or `Status` responses on the lifecycle lane.
- **Deps:** T-006

### T-008 — Crash-loop backoff *(S2)*

- **Goal:** Exponential backoff (cap 30 min, no attempt cap) on agent respawn within a short window.
- **Spec FRs:** FR-007.
- **Exit test:** `tests/orchestrator/test_backoff.py` — 10 immediate exits land at ≥30 min retry within ~10 attempts.
- **Deps:** T-006

### T-009 — Sandbox runtime adapter *(S5)* ⚠

- **Goal:** Pluggable interface `SandboxRuntime` with two impls: `DockerRuntime` (MVP, network-policy sidecar) and `FirecrackerRuntime` (production stub returning `NotImplemented` until P5).
- **Spec FRs:** FR-107, FR-108.
- **Principles:** IX (boundary in infrastructure, not prompt).
- **Exit test:** `tests/sandbox/test_egress.py` — agent inside Docker sandbox cannot reach a host outside the allowlist regardless of agent code; `tests/sandbox/test_fs.py` — write to non-`/work` path raises EROFS.
- **Deps:** T-001

### T-010 — Stub agent + chaos test *(S3)*

- **Goal:** Minimal agent that claims, heartbeats every 30 s, releases. Used to validate the substrate.
- **Exit test:** `tests/chaos/test_kill_loop.py` — kill agent every 10 s for 5 minutes; no work lost, no double-claim, no orphaned claims.
- **Deps:** T-004, T-006, T-009

---

## Phase P1 — Index gate

**Phase exit:** Indexer produces a queryable index of a 100k-LOC target; FR-003 gate releases the rest of the fleet.

### T-101 — tree-sitter frontend (Python, Go) *(S5)* ⚠

- **Goal:** Deterministic parser producing function inventory and call graph for Python and Go.
- **Spec FRs:** FR-020, FR-021. **No LLM as sole source.**
- **Exit test:** `tests/indexer/test_parser.py` — golden files for both languages match expected symbol/call-graph output.
- **Deps:** T-001

### T-102 — tree-sitter frontend (TypeScript, Java) *(S5)*

- **Goal:** Same as T-101 for TS and Java.
- **Deps:** T-101

### T-103 — Index query interface *(S3)*

- **Goal:** Implement get-function-body, get-callers, get-callees, find-symbol, full-text search over the parsed index.
- **Spec FRs:** FR-022.
- **Exit test:** Each query type returns correct results on a fixture target; unknown-symbol returns empty, not error.
- **Deps:** T-101

### T-104 — Atomic index persist *(S3)* ⚠

- **Goal:** Write index to a new generation directory, then `rename(2)` swap. Never delete-then-write.
- **Spec FRs:** FR-025, FR-106a.
- **Principles:** XI.
- **Exit test:** `tests/indexer/test_atomic_persist.py` — `kill -9` injected mid-write leaves either old or new index intact, never empty.
- **Deps:** T-103

### T-105 — Incremental re-index *(S5)*

- **Goal:** On re-run, only changed files re-parsed; call graph patched, not rebuilt.
- **Spec FRs:** FR-026.
- **Exit test:** Re-run on unchanged target re-parses zero files; touching one file re-parses one file plus its dependents.
- **Deps:** T-103

### T-106 — Scope enforcement *(S2)*

- **Goal:** Honor `target.include`/`target.exclude` glob patterns; refuse to index outside scope.
- **Spec FRs:** FR-027.
- **Exit test:** Excluded paths produce no symbols.
- **Deps:** T-103

### T-107 — Indexer process model *(S3)* ⚠

- **Goal:** Indexer runs in its own process; never blocks Orchestrator event loop.
- **Spec FRs:** FR-029.
- **Exit test:** During a 5-minute index of a large target, Orchestrator `Status` p99 latency stays under 100 ms.
- **Deps:** T-103, T-006

### T-108 — Index-gate signal *(S2)* ⚠

- **Goal:** Indexer signals `queryable` only when FR-020, FR-021, FR-022 all satisfied. Orchestrator `FR-003` gates non-Indexer spawn on this signal.
- **Spec FRs:** FR-003, FR-024.
- **Exit test:** With Indexer stalled, no other role spawns; on signal, full fleet spawns.
- **Deps:** T-101, T-103, T-006

### T-109 — pgvector embeddings (post-gate) *(S3)*

- **Goal:** Mistral embeddings stored in `pgvector`. Runs after FR-024 releases.
- **Spec FRs:** FR-023.
- **Exit test:** Similarity query returns semantically related symbols; gate release does not wait on this.
- **Deps:** T-104, T-201 (Mistral client)

---

## Phase P2 — Detection → Reporting (rule-sweep MVP)

**Phase exit:** One end-to-end run produces a SARIF file with ≥1 evidence-gated finding from a known-vulnerable fixture target.

### T-201 — Mistral client wrapper *(S3)* ⚠

- **Goal:** Thin wrapper around `mistralai` SDK exposing `complete(messages, tools, tier)` with two tiers (`strong`=Mistral Large, `bulk`=Mistral Small/Codestral). Adaptive backoff on 429 / `Retry-After`.
- **Spec FRs:** §11.2 contract.
- **Principles:** V (no internal cap; respect provider signals only).
- **Exit test:** `tests/llm/test_mistral_backoff.py` — 429 with `Retry-After: 10` triggers 10 s wait fleet-wide; sustained 5xx on `strong` degrades to `bulk`.
- **Deps:** T-001

### T-202 — Prompt-cache integration *(S2)*

- **Goal:** Enable Mistral `prompt_cache` for stable prefixes; measure hit rate.
- **Exit test:** Repeated calls with same prefix report cache hits in metrics.
- **Deps:** T-201

### T-203 — Agent harness *(S5)*

- **Goal:** Tool-use loop: system prompt + tools + steer/interrupt support + structured session log + token accounting.
- **Spec FRs:** §11.8 contract.
- **Exit test:** Harness runs a simple "echo" tool loop; mid-session steer message is delivered; session log replayable.
- **Deps:** T-201

### T-204 — Detector: Semgrep rule-sweep mode *(S5)*

- **Goal:** FR-037 — function-granularity Semgrep + LLM check per rule per function. Emits `Candidate` rows.
- **Spec FRs:** FR-037, FR-041.
- **Exit test:** On fixture target with N planted vulns, Detector queues ≥N candidates with correct fingerprints.
- **Deps:** T-103, T-203

### T-205 — Detector: dependency scan *(S2)*

- **Goal:** FR-038 — OSV-Scanner integration emits `Candidate` rows for dependencies with known CVEs.
- **Exit test:** Fixture `requirements.txt` with known-vulnerable pin produces a candidate.
- **Deps:** T-203

### T-206 — Detector: secret scan *(S2)*

- **Goal:** FR-039 — gitleaks integration emits `Candidate` rows for hardcoded secrets.
- **Exit test:** Fixture file with planted AWS key → candidate.
- **Deps:** T-203

### T-207 — Triager with citation resolver *(S8)* ⚠

- **Goal:** For each candidate, run an investigation that produces a `Verdict` with citations. Insert via T-003 trigger; fabricated citations rejected at the DB layer.
- **Spec FRs:** FR-051, FR-052, §7.3 evidence gate.
- **Principles:** I (this is the role where Principle I lives at runtime).
- **Exit test:** Fabricated-citation verdict rejected by DB; verdicts surviving the gate cite resolvable code.
- **Deps:** T-003, T-103, T-203, T-204

### T-208 — Reporter: SARIF + Markdown *(S5)*

- **Goal:** Reporter reads `verdicts WHERE verdict='true-positive' AND survived_gate=true` and emits SARIF 2.1.0 + Markdown rollup.
- **Spec FRs:** §5.8, FR-044.
- **Principles:** II (only surviving findings reach output).
- **Exit test:** SARIF validates against schema; rejected verdicts do not appear.
- **Deps:** T-207

### T-209 — End-to-end MVP run *(S3)*

- **Goal:** Single-command `make e2e` runs Orchestrator → Indexer → Detector (rule-sweep) → Triager → Reporter on fixture target.
- **Exit test:** `tests/e2e/test_mvp.py` — produces a SARIF with ≥1 evidence-gated finding; entire run reproducible.
- **Deps:** T-108, T-204, T-207, T-208

---

## Phase P3 — Cartographer + exploratory detection + multi-dim coverage

**Phase exit:** Coverage-complete signal fires only when all four coverage dimensions are credibly attempted.

### T-301 — Cartographer document pipeline *(S8)*

- **Goal:** Pipeline of one LLM pass per document type: architecture overview, attack-surface, trust-boundaries, data-flows, threat-model. Each persisted atomically.
- **Spec FRs:** FR-030, FR-031, FR-032, FR-033, FR-034, FR-035.
- **Exit test:** Each document non-empty on fixture target; persisted via FR-025 atomic swap.
- **Deps:** T-104, T-203

### T-302 — Cartographer fallback *(S2)* ⚠

- **Goal:** If a pass returns empty, write a mechanically-derived stub from index + testbed config.
- **Spec FRs:** FR-036a.
- **Exit test:** Pass forced to return empty → fallback content present, never empty document.
- **Deps:** T-301

### T-303 — Soft gate on Triager spawn *(S2)*

- **Goal:** Delay Triager spawn up to 120 s for initial security map; spawn anyway after timeout.
- **Spec FRs:** plan §1.3, FR-036.
- **Exit test:** With Cartographer stalled, Triager spawns at 120 s; with Cartographer fast, Triager spawns immediately on first map document.
- **Deps:** T-301, T-006

### T-304 — Detector exploratory mode *(S8)*

- **Goal:** FR-040 — agent with goals + security map + testbed description in context, free to investigate, with read access to source and (where configured) network access to testbed.
- **Spec FRs:** FR-040.
- **Exit test:** On a fixture with a design-level flaw not covered by any rule, exploratory agent surfaces a candidate.
- **Deps:** T-203, T-301

### T-305 — Coverage-Guide multi-dim state *(S5)* ⚠

- **Goal:** Implement `CoverageState` with four dimensions (entry_points, cwe_classes, trust_boundaries, operator_goals). Status transitions: `untouched → in_progress → credibly_attempted`.
- **Spec FRs:** §5.7.
- **Principles:** VI (auto-stop conjunction).
- **Exit test:** `tests/coverage/test_dimensions.py` — auto-stop signal fires only when all four dims = `credibly_attempted` AND yield < threshold; never on yield alone.
- **Deps:** T-301

### T-306 — Coverage-Guide directed task queueing *(S3)*

- **Goal:** From the operator's goals + security map, queue directed Detector and Triager tasks targeting under-covered dimensions.
- **Exit test:** Untouched entry point produces a queued exploratory task within one Coverage-Guide cycle.
- **Deps:** T-305

### T-307 — Yield calculator *(S3)*

- **Goal:** Trailing yield (findings × severity points / spend) over configurable window.
- **Spec FRs:** §9.4.
- **Exit test:** Yield decays correctly under no-finding window; recovers on new finding.
- **Deps:** T-305

---

## Phase P4 — Validator (Principle VII)

**Phase exit:** One finding marked `exploited` from end-to-end clean-room reproduction in a fresh microVM.

### T-401 — Firecracker runtime impl *(S8)* ⚠

- **Goal:** Replace the `NotImplemented` stub from T-009 with a real Firecracker microVM runtime. Per-agent VM, egress allowlist enforced at network namespace.
- **Spec FRs:** FR-107, FR-108.
- **Principles:** IX.
- **Exit test:** Same egress/FS tests as T-009 but on Firecracker; agent root inside VM cannot escape allowlist.
- **Deps:** T-009

### T-402 — Validator: PoC author agent *(S5)*

- **Goal:** Given a `Verdict` claiming exploitability, draft an exploit artifact (PoC script + expected impact statement). Writes to substrate but does NOT set `exploited`.
- **Spec FRs:** §5.6.
- **Exit test:** PoC artifact produced for a true-positive verdict on fixture target.
- **Deps:** T-207, T-401

### T-403 — Validator: independent runner *(S5)* ⚠

- **Goal:** Fresh agent in fresh microVM receives only `(Fingerprint, exploit_artifact_uri, testbed description)`. Runs the PoC, observes impact. Sets `exploited` only on observed headline impact match.
- **Spec FRs:** FR-060, §7.4.
- **Principles:** VII (independence enforced by `runner_agent_id != poc_author_agent_id` DB constraint from T-002).
- **Exit test:** `tests/validator/test_independence.py` — DB rejects ExploitProof with same author and runner; successful proof requires distinct agent identities.
- **Deps:** T-401, T-402

### T-404 — Testbed binding *(S3)*

- **Goal:** From `testbed` config (§12), provision agent VM with read-only testbed description and (if specified) network reachability.
- **Spec FRs:** §11.12 contract.
- **Exit test:** Validator VM can reach configured testbed host; cannot reach any other host.
- **Deps:** T-401

---

## Phase P5 — Multi-tenancy + production hardening

**Phase exit:** Two evaluations run concurrently on one cluster with NFR-003 holding under fuzzed substrate queries.

### T-501 — Kubernetes deployment manifests *(S5)*

- **Goal:** One namespace per evaluation; `NetworkPolicy` enforcing egress allowlist; `PodSecurityPolicy` matching sandbox requirements.
- **Spec FRs:** §11.5.
- **Exit test:** `kind` cluster runs two evaluations side-by-side; `NetworkPolicy` blocks cross-namespace traffic.
- **Deps:** T-401

### T-502 — Row-level security policies *(S3)* ⚠

- **Goal:** Postgres RLS policies on every substrate table keyed on `evaluation_id`; per-evaluation database role.
- **Spec FRs:** NFR-003.
- **Exit test:** `tests/sql/test_rls_fuzz.py` — 10k fuzzed cross-evaluation queries, zero leaks.
- **Deps:** T-002

### T-503 — Per-evaluation GitHub App auth *(S3)*

- **Goal:** Short-lived per-role tokens minted from per-evaluation GitHub App installation.
- **Spec FRs:** §11.7.
- **Exit test:** Issue actions audit-trail shows the role identity, not a shared service account.
- **Deps:** T-501

### T-504 — Conversational lane scaling *(S2)*

- **Goal:** Conversational worker pool scales independently of fleet size.
- **Spec FRs:** FR-019, NFR-006.
- **Exit test:** 10 concurrent operator queries do not affect lifecycle lane latency.
- **Deps:** T-007

### T-505 — Observability: OpenTelemetry + Prometheus + dashboard *(S5)*

- **Goal:** Per-finding audit chain (NFR-007); metrics named in plan §5; Next.js dashboard.
- **Spec FRs:** §10, NFR-007.
- **Exit test:** Given a finding ID, reconstruct Detector → Triager → Validator → Reporter session logs from telemetry alone.
- **Deps:** T-208, T-403

### T-506 — Hot reload (budget, rules) *(S3)*

- **Goal:** FR-128 — runtime reload of `budget` and `rules` config without restart.
- **Exit test:** Mid-run `budget.spend_cap` increase takes effect within one Orchestrator cycle.
- **Deps:** T-006

### T-507 — Operator override path *(S3)*

- **Goal:** Every automated decision (verdict, exploited, coverage-complete, auto-stop) overridable by operator; override written to `overrides` table with operator identity and reason.
- **Spec FRs:** NFR-009, FR-018.
- **Principles:** X.
- **Exit test:** Override applied; original automated decision preserved in audit chain.
- **Deps:** T-208

### T-508 — Resumability tests *(S3)*

- **Goal:** Every long-running stage resumable from last checkpoint after process death.
- **Spec FRs:** NFR-001.
- **Exit test:** Kill each role mid-stage; on respawn, work resumes from checkpoint, no duplicate work.
- **Deps:** T-104, T-301, T-204

---

## Cross-cutting tasks (parallel to P0–P5)

### T-901 — Configuration schema (YAML 1.2) *(S3)*

- **Goal:** Pydantic models for `target`, `testbed`, `goals`, `rules`, `detection`, `fleet`, `sandbox`, `budget`, `integrations`. Validation surfaces all errors at once (FR-010).
- **Spec FRs:** §12, FR-126, FR-127, FR-129.
- **Exit test:** Sample config with three errors reports all three; valid config validates.
- **Deps:** T-001

### T-902 — Secrets reference resolver *(S2)*

- **Goal:** Resolve `${env:NAME}` and `${kms:path}` references at config load; never log secret values.
- **Spec FRs:** FR-127, NFR-008.
- **Deps:** T-901

### T-903 — `/speckit.analyze` integration *(S2)*

- **Goal:** Wire constitution-conformance check into CI so plan or task changes that violate principles fail PR.
- **Exit test:** Synthetic PR introducing a 5-min wall-clock liveness check fails CI with Principle III citation.
- **Deps:** T-001

### T-904 — Chaos / fuzz harness *(S5)*

- **Goal:** Reusable chaos test runner: random `kill -9`, network partitions, provider 429 storms, RLS query fuzzing.
- **Used by:** T-010, T-403, T-502.
- **Deps:** T-001

---

## Dependency graph (high-level)

```
T-001
 ├─ T-002 ─ T-003 (Principle I gate) ─┐
 │       └─ T-004 (Principle III/IV) ─┤
 ├─ T-005 ─ T-006 ─ T-007 ─ T-504    │
 │              └─ T-008             │
 ├─ T-009 ─ T-401 ─ T-501 ─ T-503    │
 ├─ T-101 ─ T-102                    │
 │      ├─ T-103 ─ T-104 ─ T-105     │
 │      │       └─ T-106             │
 │      └─ T-107 ─ T-108 ◀─── gate ──┤
 │                                   │
 ├─ T-201 ─ T-202 ─ T-203 ─ T-204 ──▶┤
 │                       ├─ T-205    │
 │                       ├─ T-206    │
 │                       └─ T-207 ──▶┤  (uses T-003 gate)
 │                              └─ T-208 ─ T-209 ─ T-507
 ├─ T-301 ─ T-302 ─ T-303 ─ T-304 ─ T-305 ─ T-306 ─ T-307
 ├─ T-402 ─ T-403 ─ T-404
 ├─ T-502 ─ T-505 ─ T-506 ─ T-508
 └─ T-901 ─ T-902 ─ T-903 ─ T-904
```

---

## Effort summary

| Phase | Tasks | Story points |
|---|---:|---:|
| P0 Substrate | 10 | 33 |
| P1 Index gate | 9 | 31 |
| P2 Detection → Reporting | 9 | 33 |
| P3 Cartographer + coverage | 7 | 31 |
| P4 Validator | 4 | 21 |
| P5 Multi-tenancy + hardening | 8 | 27 |
| Cross-cutting | 4 | 12 |
| **Total** | **51** | **188** |

---

## Constitution compliance — tasks enforcing each principle

| Principle | Enforcing tasks |
|---|---|
| I. Evidence Over Assertion | T-003 ⚠, T-207 ⚠ |
| II. Surface Only What Survives | T-208 |
| III. Liveness By Heartbeat | T-004 ⚠, T-006, T-010 |
| IV. Claims Atomic & Mortal | T-002 ⚠, T-004 ⚠ |
| V. Provider Is Rate Arbiter | T-201 ⚠ |
| VI. Coverage Before Yield | T-305 ⚠, T-307 |
| VII. Exploited Means Demonstrated | T-403 ⚠, T-002 ⚠ |
| VIII. Stable Fingerprints | T-002 ⚠ |
| IX. Sandbox By Infrastructure | T-009 ⚠, T-401 ⚠ |
| X. Operator Outranks Agents | T-507 |
| XI. Persist Atomically | T-002 ⚠, T-104 ⚠ |

A ⚠ task that ships without its exit test passing breaks a constitutional invariant. These are the tasks PR review must hold the line on.

---

## Open work not yet decomposed

- Extension roles (§6) — Deep-Tester, Variant-Hunter, Attack-Mapper, Remediator, Self-Improver. Decompose at plan v0.2 once the core pipeline produces validated, exploited findings end-to-end.
- Cross-provider LLM failover (plan §9 item 6).
- Compliance mapping to a specific framework (plan §9 item 1).
- Severity scheme adoption (plan §9 item 5).

---

*End of tasks. Run `/speckit.analyze` to verify constitutional conformance against `plan.md` 0.1.0 and `constitution.md` 0.2.0 before claiming the first task.*
