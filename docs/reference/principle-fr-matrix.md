# Principle × FR Matrix

**Audience:** maintainers running the constitution's [§Compliance review](../../constitution.md#compliance-review):

> the coverage matrix (each principle → enforcing FRs) is regenerated and any GAP row blocks the release.

This is that matrix. It is regenerated at every MINOR-or-greater release of the seed; a GAP row (a principle with no enforcing FRs) blocks the release.

## Conventions

- **Principle** column: the constitutional principle by number.
- **Primary FR(s)** column: the FRs that exist *because* of the principle. If they were removed, the principle would not be enforced.
- **Supporting FR(s)** column: FRs that interact with the principle but are not the primary enforcement mechanism.
- **Status** column: `OK` if at least one primary FR exists; `GAP` if not. A `GAP` blocks release.

If this matrix and the spec disagree, the spec wins; this page is updated.

## Matrix

| Principle | Title | Primary FR(s) | Supporting FR(s) | Status |
|---|---|---|---|---|
| I | [Evidence Over Assertion](../../constitution.md#i-evidence-over-assertion) | FR-087, FR-087a, FR-088 | FR-053–FR-058 (Triager), FR-059–FR-064 (Validator), FR-085, FR-086 | OK |
| II | [Surface Only What Survives](../../constitution.md#ii-surface-only-what-survives) | FR-044, FR-057, FR-079 | FR-042 (rule-gap), FR-045 (dedup), FR-078 (publish true-positive reports), FR-086 (retain rejected), FR-090–FR-091 (fingerprint), FR-092 (label set) | OK |
| III | [Liveness By Heartbeat, Never By Clock](../../constitution.md#iii-liveness-by-heartbeat-never-by-clock) | FR-005, FR-100, FR-101 | FR-007 (crash-loop backoff), FR-118 (session rotation, *not* liveness) | OK |
| IV | [Claims Are Atomic And Mortal](../../constitution.md#iv-claims-are-atomic-and-mortal) | FR-095, FR-096 | FR-097 (auto-block on N releases), FR-098 (operator-/agent-writable), FR-099 (stable ids) | OK |
| V | [The Provider Is The Rate Arbiter](../../constitution.md#v-the-provider-is-the-rate-arbiter) | FR-105, FR-106 | FR-113 (cost/token tracking) | OK |
| VI | [Coverage Before Yield](../../constitution.md#vi-coverage-before-yield) | FR-115, FR-116, FR-117 | FR-067–FR-071 (Coverage-Guide), FR-114 (default unset) | OK |
| VII | [Exploited Means Demonstrated](../../constitution.md#vii-exploited-means-demonstrated) | FR-060, FR-061, FR-089 | FR-062–FR-064 (Validator behavior) | OK |
| VIII | [Fingerprints Are Stable Under Edit](../../constitution.md#viii-fingerprints-are-stable-under-edit) | FR-090, FR-091 | FR-045 (dedup keys on fingerprint), FR-080 (Reporter dedup), FR-058 (cross-run inheritance) | OK |
| IX | [Sandbox By Infrastructure, Not By Prompt](../../constitution.md#ix-sandbox-by-infrastructure-not-by-prompt) | FR-107, FR-108 | FR-109 (operator informed of pivot points), FR-110, FR-111 (hard rules as defense-in-depth) | OK |
| X | [The Operator Outranks Every Agent](../../constitution.md#x-the-operator-outranks-every-agent) | FR-014, FR-016, FR-018, FR-102 | FR-013 (grounded answers), FR-015 (help requests), FR-110, FR-119a (no busywork) | OK |
| XI | [Persist Atomically](../../constitution.md#xi-persist-atomically) | FR-106a | FR-025 (Indexer instance), FR-074 (Coverage-Guide checklist instance) | OK |

All eleven principles have at least one Primary FR. **No GAP rows.** Status: matrix passes.

## Notes per principle

### I — Evidence Over Assertion

FR-087 and FR-088 make the verdict structurally checkable (three-leg evidence) and mechanically checked (citations resolve). FR-087a is the narrow carve-out for presence-is-the-vulnerability classes.

### II — Surface Only What Survives

The Detector cannot directly surface (FR-044). The Triager surfaces only `true-positive` findings via Reporter (FR-057). The Reporter must not publish any non-`true-positive` finding (FR-079). Each of those is a primary enforcer — removing any one of them re-introduces the failure.

### III — Liveness By Heartbeat, Never By Clock

FR-005 forbids wall-clock as a liveness signal. FR-100 defines liveness as heartbeat age. FR-101 requires the heartbeat to have its own execution lane.

### IV — Claims Are Atomic And Mortal

FR-095 (atomicity) and FR-096 (mortality). Both are required; either alone reproduces a different failure mode.

### V — The Provider Is The Rate Arbiter

FR-105 forbids internal pre-throttling below the provider's actual limit. FR-106 requires shared backoff state across the fleet.

### VI — Coverage Before Yield

FR-116 is the conjunction (yield low AND coverage complete AND minimum runtime AND trailing window full). FR-115 defines yield. FR-117 makes the parameters operator-configurable.

### VII — Exploited Means Demonstrated

FR-089 anchors `exploited` to Validator-only setting after testbed reproduction. FR-060/FR-061 define what reproduction means.

### VIII — Fingerprints Are Stable Under Edit

FR-090 defines the fingerprint structure (path + symbol + class). FR-091 keys deduplication on it. The exclusions (line numbers, snippets, timestamps) are normative in FR-090.

### IX — Sandbox By Infrastructure, Not By Prompt

FR-107 mandates infrastructure enforcement. FR-108 requires read-only mounts. Together they make the boundary unarguable.

### X — The Operator Outranks Every Agent

FR-014 (operator submits tasks at chosen priority), FR-016 (operator steers running agents), FR-018 (conversational facet does not modify verdicts on its own initiative), FR-102 (peer messages are advisory). The pattern is consistent: operator authority is structurally superior to agent claims.

### XI — Persist Atomically

FR-106a is the general rule. FR-025 and FR-074 are instances of it (Indexer index, Coverage-Guide checklist). Removing FR-106a would not by itself remove FR-025 / FR-074, but the general rule is required so future persisted artifacts inherit the guarantee.

## Procedure: regenerate this matrix

When `constitution.md` changes at MINOR or above (or `spec.md` changes in a way that adds/removes a principle-enforcing FR):

1. Walk each principle in [`constitution.md`](../../constitution.md).
2. Identify the FR(s) whose existence is *because of* the principle (Primary).
3. Identify the FR(s) that interact with the principle without being primary (Supporting).
4. Mark `OK` if Primary is non-empty, `GAP` if empty.
5. If any row is `GAP`, the release is blocked until either an FR is added or the principle is removed (with full Amendment process; see [`../governance/amendment-process.md`](../governance/amendment-process.md)).

Record the result in this file and reference it in the Sync Impact Report at the top of `constitution.md`.

## See also

- [`fr-index.md`](fr-index.md) — one-line summaries of every FR.
- [`../../constitution.md`](../../constitution.md) — the principles themselves.
- [`../governance/amendment-process.md`](../governance/amendment-process.md) — the amendment procedure when a principle no longer fits.
- [`../principles/anti-patterns.md`](../principles/anti-patterns.md) — failure modes per principle.
