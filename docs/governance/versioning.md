# Versioning Policy

**Audience:** maintainers deciding which version-component to bump on a change to `spec.md` or `constitution.md`.

The versioning rules are normative in [`constitution.md` §Versioning policy](../../constitution.md#versioning-policy) (for the constitution itself; the spec uses the same scheme). This page gives concrete examples per tier.

## Scheme

```
MAJOR.MINOR.PATCH
```

For both `spec.md` and `constitution.md`:

- **MAJOR** — a normative inversion or a structural addition/removal.
- **MINOR** — scope widened or narrowed without inverting; rationale materially extended; a Governance subsection added.
- **PATCH** — wording, cross-reference, and formatting fixes with no change to what any principle requires.

Every version change updates the Sync Impact Report at the top of `constitution.md`.

## Constitution: examples by tier

### PATCH (no normative change)

- Fix a typo in a principle's rationale paragraph.
- Add a missing cross-reference to an FR.
- Reformat a list for consistency.
- Update the "Last sync" timestamp.

These do not change what any principle requires; readers' obligations are unchanged.

### MINOR (scope shift, no inversion)

- **Existing example: 0.1.0 → 0.2.0 narrowed Principle III.** Original phrasing forbade wall-clock-based termination outright, including session rotation. The narrowing carved out FR-118 explicitly: wall-clock MAY trigger session rotation; it MUST NOT trigger claim reclamation. The "MUST NOT" intent on liveness is unchanged; the scope is narrower.
- Adding a Governance subsection (e.g., a new "Compliance review" subsection).
- Materially extending a rationale paragraph with case studies.
- Widening a principle's applicability (e.g., from "the index" to "every persisted artifact more than one component reads", which is exactly how Principle XI was generalized internally before the seed shipped).

### MAJOR (normative inversion or structural change)

- Adding a new principle (e.g., a hypothetical Principle XII).
- Removing an existing principle entirely.
- Inverting a principle's normative direction. Example (hypothetical): turning Principle III from "MUST NOT use wall-clock for liveness" into "MAY use wall-clock for liveness". The seed authors do not anticipate ever doing this; if you propose it, expect deep scrutiny.
- Splitting a principle into two (or merging two into one).

A MAJOR bump is uncommon. The seed shipped at 0.x and is expected to remain there for a while, with MAJOR reserved for genuinely structural changes after broad adoption.

## Spec: examples by tier

The spec uses the same scheme.

### PATCH

- Wording fix in an FR's rationale paragraph (no change to what the FR requires).
- Renumbering examples (no change to FR numbers themselves; FR ids are stable for a major version).
- Cross-reference fix.

### MINOR

- New FR added that satisfies an existing principle better.
- Existing FR scope narrowed (e.g., adding a carve-out like FR-087a).
- New section added for a clarification axis (e.g., a new §11.X surface).

### MAJOR

- Removing an FR.
- Renumbering FRs (which breaks references in plans, tasks, and reviews — avoid unless absolutely necessary).
- Restructuring sections in a way that breaks anchor links from external documents.

## Tying it together: typical change → bump

| Typical change | spec | constitution |
|---|---|---|
| Fix a typo | PATCH | PATCH |
| Add a worked example to a rationale | PATCH or MINOR (case dependent) | MINOR (rationale materially extended) |
| Add an FR to enforce a principle better | MINOR | n/a |
| Add a carve-out to an FR | MINOR | n/a |
| Narrow a principle's scope | n/a | MINOR (existing 0.2.0 example) |
| Remove an FR | MAJOR | n/a |
| Add a principle | n/a | MAJOR |
| Invert a principle | n/a | MAJOR (and do not do this lightly) |

## Update procedure

Whenever the version bumps:

1. Update the version field in the file's metadata block.
2. Update the [Sync Impact Report](sync-impact-reports.md) header in `constitution.md` (even when the change is to the spec — note the spec change there if it touches downstream re-checks).
3. Add a CHANGELOG entry (see [`../../CHANGELOG.md`](../../CHANGELOG.md)).
4. Re-run `/speckit.analyze` and the principle × FR matrix regeneration ([`../reference/principle-fr-matrix.md`](../reference/principle-fr-matrix.md)).
5. Update the README's version badge if it references the spec or constitution version.

## Anti-patterns

- **"Bump MAJOR to be safe."** Don't. MAJOR has costs: every downstream consumer audits.
- **"Skip the bump because the change is small."** Every change ships with a version reflecting its impact. PATCH is fine for small wording fixes; the goal is honest semantics, not low numbers.
- **"Bump just the file without updating the Sync Impact Report."** The header is the audit trail.

## See also

- [`amendment-process.md`](amendment-process.md) — procedure for proposing changes.
- [`sync-impact-reports.md`](sync-impact-reports.md) — the report format.
- [`../../constitution.md#versioning-policy`](../../constitution.md#versioning-policy) — the canonical scheme.
- [`../../CHANGELOG.md`](../../CHANGELOG.md) — the seed's version history.
