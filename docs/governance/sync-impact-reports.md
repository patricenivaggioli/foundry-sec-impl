# Sync Impact Reports

**Audience:** maintainers writing or reviewing the Sync Impact Report block at the top of [`constitution.md`](../../constitution.md).

The block exists to make every constitutional change auditable: which principles were touched, which downstream artifacts must be re-verified, and what follow-up work remains. This page describes the format and archives prior reports as the constitution evolves.

## The format

The Sync Impact Report is a comment block at the very top of `constitution.md`, regenerated on every constitution change:

```
<!--
SYNC IMPACT REPORT — maintained by /speckit.constitution
═══════════════════════════════════════════════════════
Version change   : <prev> → <next>  [<MAJOR|MINOR|PATCH>: <reason>]
Principles       : <which principles changed and how>
Sections changed : <numbered sections>
Templates needing update : <files in .specify/ or n/a>
Downstream re-check      : <per the table in §Downstream artifacts>
Follow-up TODOs  : <or "none">
Last sync        : <YYYY-MM-DD>
═══════════════════════════════════════════════════════
This block is regenerated on every constitution change; do not hand-edit below the rule.
-->
```

The block is **regenerated**, not appended. Each constitution change replaces the contents in place; the prior contents are preserved by Git history (and archived below for important transitions).

## Field semantics

### `Version change`

Format: `<prev> → <next>`, where each is `MAJOR.MINOR.PATCH`, followed by `[<tier>: <one-line reason>]`.

The tier MUST match the change semantics:

- `MAJOR` — principle added/removed/inverted.
- `MINOR` — scope widened/narrowed; rationale materially extended; new Governance subsection.
- `PATCH` — wording, cross-reference, formatting only.

See [`versioning.md`](versioning.md) for examples.

### `Principles`

For each principle touched, name it (by Roman numeral) and describe the change in one phrase.

Examples:

- `III narrowed (work-reclamation only; session rotation per FR-118 carved out)`
- `XII added (PRINCIPLE_NAME: …)`
- `IV rationale extended with [scenario] case study`

### `Sections changed`

The §-numbered sections affected. The Roman-numeral principle list is **not** the same as the section list — Governance changes have section names like `§Compliance review`.

### `Templates needing update`

If templates under `.specify/` (or your spec-kit installation's equivalent) reference the constitution, list them. Templates that need re-rendering go here.

If none, write `n/a`.

### `Downstream re-check`

Per the table in [`constitution.md` §"Downstream artifacts re-checked on change"](../../constitution.md#downstream-artifacts-re-checked-on-change), confirm the result of each check:

```
Downstream re-check : spec.md FR-005, FR-118 ✓  README.md ✓  plan.md n/a  tasks.md n/a
```

`✓` means re-checked and passes. `✗` means re-checked and fails (which would block the merge). `n/a` means the artifact does not exist.

### `Follow-up TODOs`

Anything that came out of the review but cannot land in this PR. Should ideally be `none`. If non-empty, link to issues.

### `Last sync`

ISO date `YYYY-MM-DD`. The day the report was last generated.

## When to regenerate

The report is regenerated whenever:

- `constitution.md` changes (any tier).
- A spec change forces re-validation of the *Downstream re-check* table (e.g., a removed FR that previously enforced a principle).
- A maintainer audits the sync state without a code change (rare; usually paired with `Last sync` bump only and `Follow-up TODOs: none`).

## Reading the report as a reviewer

When reviewing a constitution-touching PR:

1. Check `Version change` matches the actual change (per [`versioning.md`](versioning.md)).
2. Check `Principles` enumerates every principle the diff touches.
3. Check `Sections changed` matches the diff.
4. Check `Downstream re-check` lists every required artifact and that each is `✓` or `n/a`.
5. If `Follow-up TODOs` is non-empty, confirm they have linked issues.

If any check fails, the PR is not ready.

## Archive of prior reports

These are preserved here as a navigable history. Git is authoritative; this archive is for convenience.

### 0.1.0 → 0.2.0 (current as of writing — see `constitution.md`)

```
Version change   : 0.1.0 → 0.2.0  [MINOR: III scope narrowed]
Principles       : III narrowed (work-reclamation only; session rotation per FR-118 carved out)
Sections changed : III
Templates needing update : n/a
Downstream re-check      : spec.md FR-005, FR-118 ✓  README.md ✓  plan.md n/a  tasks.md n/a
Follow-up TODOs  : none
Last sync        : 2026-05-04
```

**Why:** the original phrasing of III forbade wall-clock-based termination outright, which over-constrained legitimate session rotation under FR-118. The narrowing carved out FR-118 explicitly — wall-clock MAY trigger session rotation; it MUST NOT trigger claim reclamation. The "no liveness misfire" intent is unchanged.

### Future entries

When the constitution next changes, a new entry appears here, *above* the current entry, dated and tier-tagged. The constitution itself shows only the most recent block; this archive carries the trail.

## See also

- [`amendment-process.md`](amendment-process.md) — the procedure that produces these reports.
- [`versioning.md`](versioning.md) — concrete examples of each version tier.
- [`../../constitution.md`](../../constitution.md) — the canonical principles and the live block.
