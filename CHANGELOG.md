# Changelog

All notable changes to the **Foundry Security Spec** seed repository.

This CHANGELOG covers the seed itself (the artifacts at this repository's root and under `docs/`). It does **not** cover any Foundry-derived implementation; downstream consumers maintain their own changelogs.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely; versioning follows [`docs/governance/versioning.md`](docs/governance/versioning.md) and [`constitution.md` §Versioning policy](constitution.md#versioning-policy).

The seed has two independently-versioned normative artifacts:

- **`spec.md`** — currently versioned alongside the seed.
- **`constitution.md`** — independently versioned; current version `0.2.0` (see the Sync Impact Report block at the top of the file).

When either changes at MINOR or above, a new entry below records the diff and the downstream re-checks performed.

## [Unreleased]

### Added

- `docs/` directory: index, adoption guides (quickstart, clarification playbook, integration decisions, extension roles), architecture views (role interactions, finding lifecycle, substrate contracts, rule-gap flywheel), principles anti-patterns, worked examples (clarification, detection rule, evidence gate), reference tables (FR index, principle × FR matrix, open-questions checklist, terminology quick card), governance how-tos (amendment process, versioning, sync impact reports), operations guides (observability checklist, sandbox patterns, budget and stop conditions), and FAQ.
- Root `GLOSSARY.md` — standalone glossary mirrored from `spec.md` §2 (referenced by README's *What's in this repository* table; previously missing).
- Root `CHANGELOG.md` — this file (referenced by README and the version badge; previously missing).

### Changed

- *(none — all additions are net-new docs that cite, but do not modify, the canonical artifacts.)*

### Removed

- *(none)*

---

## [Seed v0.1.0] — initial seed publication

### Added

- `spec.md` — the seed specification: 8 core agent roles, 5 extension roles, finding lifecycle, coordination substrate, governance and safety requirements, ~130 functional requirements with inline rationale.
- `constitution.md` — eleven inviolable principles (originally `0.1.0`; subsequently amended to `0.2.0`, see below).
- `README.md` — adoption guide and spec-kit walkthrough.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `MAINTAINERS.md`, `SECURITY.md`, `LICENSE`, `AGENTS.md` — repository governance and contribution scaffolding.
- `.gitignore`.

### Constitution version history

| Version | Date | Tier | Summary |
|---|---|---|---|
| `0.1.0` | initial | — | Initial release with 11 principles. |
| `0.2.0` | 2026-05-04 | MINOR | Principle III scope narrowed: work-reclamation only; session rotation per FR-118 carved out. See the `SYNC IMPACT REPORT` block at the top of `constitution.md` for the canonical record, and [`docs/governance/sync-impact-reports.md`](docs/governance/sync-impact-reports.md) for the archive. |

---

## How this CHANGELOG is maintained

- The `[Unreleased]` section accumulates changes between releases.
- On release, the section is renamed to the released version and a fresh `[Unreleased]` is created.
- Every entry that touches `constitution.md` MUST cross-reference the corresponding Sync Impact Report block.
- Every entry that touches `spec.md` at MINOR or above MUST list the affected FRs.

For procedural details, see [`docs/governance/amendment-process.md`](docs/governance/amendment-process.md).
