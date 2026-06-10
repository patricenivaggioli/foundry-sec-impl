# Amendment Process

**Audience:** maintainers proposing a change to `spec.md` or `constitution.md`. Contributors authoring such a change should also read this before opening a PR.

This page is the **procedural how-to** behind the [`constitution.md` §Governance](../../constitution.md#governance) section, which is normative but terse. The constitution wins on every disagreement; this page only operationalizes it.

## When to use which procedure

| Scope of change | Procedure |
|---|---|
| Wording fix in `spec.md` (no semantic change) | Standard PR; CHANGELOG note. |
| New FR / removed FR / changed FR semantics in `spec.md` | This page, "spec amendment". |
| Wording fix in `constitution.md` | This page, "constitution amendment", PATCH bump. |
| Principle scope widened or narrowed | This page, "constitution amendment", MINOR bump. |
| Principle added, removed, or normatively inverted | This page, "constitution amendment", MAJOR bump. |

See [`versioning.md`](versioning.md) for examples of each.

## Spec amendment

### 1. Open an issue

Title: `spec amend: <one-line summary>`. Body must include:

- The specific scenario the current spec produces a worse outcome for.
- The principle(s) the change interacts with (cite by number; see [`../reference/principle-fr-matrix.md`](../reference/principle-fr-matrix.md)).
- Whether the change is at the FR level or section level.
- Proposed FR diff (added text or wording change).

### 2. Confirm constitutional alignment

For every principle the change touches:

- The change must not contradict the principle. If it does, you are amending the **constitution**, not the spec — see Constitution Amendment below.
- Reference [`../principles/anti-patterns.md`](../principles/anti-patterns.md). If your proposed change matches an anti-pattern, the change is almost certainly wrong; document why your case is different.

### 3. Open the PR

PR description MUST identify (per [`constitution.md` §Compliance review](../../constitution.md#compliance-review)):

- Which principle(s) the change affects.
- The enforcing FR(s) — old and new where applicable.
- Whether the spec version bumps PATCH / MINOR / MAJOR.
- A `Sync Impact Report`-style summary at the top of the PR description (mirror the format used in `constitution.md`).

### 4. Run the conformance check

`/speckit.analyze` on the modified spec. The check must pass before review.

### 5. Update downstream artifacts

Per the table in `constitution.md` §"Downstream artifacts re-checked on change":

- README — version badge, principle count, workflow description.
- Any plan / tasks files derived from the spec — re-run `/speckit.analyze`.
- Agent prompts that reference principles by number — verify wording still matches.

### 6. Merge

Maintainers review for:

- Constitutional alignment (does it contradict any principle?).
- Failure-case grounding (is the proposed change tied to a real failure mode, not a preference?).
- FR clarity and testability.

The PR description's Sync Impact Report is included in the merge commit.

## Constitution amendment

This is the harder path. The constitution exists because each principle was hard-won; treat amendments as such.

### 1. Document the failure case

You may amend a principle only by:

> 1. Documenting the specific scenario in which the principle, as written, produces a worse outcome than violating it; and
> 2. Recording the amendment in this file with version bump, date, and rationale.

(Quoted from [`constitution.md` §Amendment](../../constitution.md#amendment).)

"It is inconvenient" and "our infrastructure makes it hard" are not grounds. Each principle was inconvenient; each one's absence was more expensive.

In the issue / PR description, include:

- The principle being amended (by number).
- The scenario where the principle, as written, produces the worse outcome.
- Empirical evidence — measurements, post-mortems, traffic logs.
- Why the failure mode the principle was originally added to prevent does *not* apply in your scenario.

### 2. Determine the version bump

| Change | Bump | Examples |
|---|---|---|
| Wording, cross-reference, formatting; no normative change | PATCH | Fix typo; clarify pronoun antecedent. |
| Scope widened or narrowed; rationale materially extended; new Governance subsection | MINOR | III narrowed (work-reclamation only) — see existing 0.1.0 → 0.2.0 in the constitution's Sync Impact Report header. |
| Principle added, removed, or normatively inverted ("never" → "may", or vice versa) | MAJOR | A new principle XII; removal of an existing principle. |

See [`versioning.md`](versioning.md) for more.

### 3. Update the Sync Impact Report

Edit the comment block at the top of `constitution.md`:

```
SYNC IMPACT REPORT — maintained by /speckit.constitution
═══════════════════════════════════════════════════════
Version change   : 0.2.0 → 0.3.0  [MINOR: <reason>]
Principles       : <which principles changed>
Sections changed : <numbers>
Templates needing update : <files>
Downstream re-check      : <per the table>
Follow-up TODOs  : <or "none">
Last sync        : <YYYY-MM-DD>
```

The format is described in [`sync-impact-reports.md`](sync-impact-reports.md).

### 4. Run downstream conformance

Per the constitution's *Downstream artifacts re-checked on change* table:

| Artifact | Check | Owner |
|---|---|---|
| `spec.md` | Every principle still has ≥1 enforcing FR; no FR contradicts a principle. | Seed maintainers |
| `README.md` | Principle count, workflow description, version badge agree. | Seed maintainers |
| `plan.md` (if generated) | `/speckit.analyze` passes. | Implementing team |
| `tasks.md` (if generated) | `/speckit.analyze` passes. | Implementing team |
| Agent prompts | Principle numbers and wording still match. | Implementing team |

If any check fails, the failure is in the downstream artifact (not in the constitution); fix the artifact.

### 5. Regenerate the principle × FR matrix

[`../reference/principle-fr-matrix.md`](../reference/principle-fr-matrix.md). If any row is `GAP`, the release is blocked. Either:

- Add an FR to the spec (cycling through "spec amendment" above), or
- Confirm the principle is being removed (which means MAJOR bump).

### 6. Open the PR

PR description MUST contain:

- The Sync Impact Report.
- A diff of the constitution.
- A diff of the principle × FR matrix.
- A diff of any spec FR(s) added or removed to keep the matrix `OK`.
- Confirmation each downstream artifact has been re-checked.

### 7. Merge

Maintainer review focuses on:

- Is the failure case real and ground-truth?
- Does the change reproduce a different failure?
- Are downstream artifacts coherent?

Maintainers may reject an amendment without alternative; the constitution does not promise that every proposed change must be accommodated.

## Anti-patterns in amendment proposals

| Pattern | Why it's wrong |
|---|---|
| "We need to relax Principle I for class X" | Carve-outs from Principle I have re-broken the system every time we tried them. The narrow FR-087a is the only one we accept. |
| "Wall-clock timeouts are simpler than heartbeat" | Principle III exists *because* simpler was wrong. |
| "Internal rate caps are good neighbors" | Principle V exists *because* internal caps were always wrong. |
| "We trust our agents not to overlap" | Principle IV exists *because* we did not. |
| "Just for development environments, …" | The principles do not have dev/prod toggles. |

If your proposal matches any of these, write the failure-case-grounding section *first*. If you cannot, the proposal is not ready.

## See also

- [`versioning.md`](versioning.md) — concrete examples of each bump tier.
- [`sync-impact-reports.md`](sync-impact-reports.md) — the Sync Impact Report format.
- [`../../constitution.md`](../../constitution.md) — the canonical principles and Governance section.
- [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) — general contribution rules.
- [`../principles/anti-patterns.md`](../principles/anti-patterns.md) — failure modes for each principle, useful when defending the status quo against amendment proposals.
