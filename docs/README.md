# Foundry Documentation

Welcome. This directory complements the canonical artifacts at the repository root — it does **not** replace them and it does **not** restate normative requirements.

## Canonical artifacts (read these first)

| File | What it is | Authority |
|---|---|---|
| [`../spec.md`](../spec.md) | The seed specification: 8 core roles, 5 extension roles, finding lifecycle, coordination substrate, ~130 functional requirements. | Normative for systems derived from the seed. |
| [`../constitution.md`](../constitution.md) | 11 inviolable principles. Each encodes a production failure that motivated it. | **Wins** against `spec.md` per Constitution §Precedence. |
| [`../README.md`](../README.md) | How to turn the seed into your own system using spec-kit. | Operator-facing. |
| [`../GLOSSARY.md`](../GLOSSARY.md) | Standalone glossary mirrored from `spec.md` §2. | Reference. |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Version history of the seed itself. | Reference. |

If anything in `docs/` conflicts with the artifacts above, the artifacts above are right and `docs/` is wrong. Open an issue.

## What's here

```
docs/
├── README.md                 ← you are here
├── faq.md                    ← curated adoption questions
├── adoption/                 ← how to take the seed into a real org
├── architecture/             ← cross-role views, diagrams, flows
├── principles/               ← anti-patterns and field guide for the 11 principles
├── worked-examples/          ← concrete case studies (clarification, rule, evidence)
├── reference/                ← lookup tables (FR index, principle×FR matrix)
├── governance/               ← procedural how-to for amendments and versioning
└── operations/               ← organization-neutral implementation patterns
```

## Audience map

**You are a security team lead deciding whether to adopt the seed.**

1. [`../README.md`](../README.md) (top to "Getting started")
2. [`adoption/quickstart.md`](adoption/quickstart.md)
3. [`worked-examples/example-clarification.md`](worked-examples/example-clarification.md)
4. [`faq.md`](faq.md)

**You are running `/speckit.clarify` right now and need help answering markers.**

1. [`adoption/clarification-playbook.md`](adoption/clarification-playbook.md)
2. [`adoption/integration-decisions.md`](adoption/integration-decisions.md)
3. [`reference/open-questions-checklist.md`](reference/open-questions-checklist.md)
4. [`adoption/extension-roles-when.md`](adoption/extension-roles-when.md)

**You are a platform engineer mapping the spec onto your stack.**

1. [`architecture/role-interactions.md`](architecture/role-interactions.md)
2. [`architecture/finding-lifecycle.md`](architecture/finding-lifecycle.md)
3. [`architecture/substrate-contracts.md`](architecture/substrate-contracts.md)
4. [`operations/sandbox-patterns.md`](operations/sandbox-patterns.md)
5. [`operations/observability-checklist.md`](operations/observability-checklist.md)

**You are reviewing a `plan.md` or `tasks.md` PR and need to defend a principle.**

1. [`principles/anti-patterns.md`](principles/anti-patterns.md)
2. [`reference/principle-fr-matrix.md`](reference/principle-fr-matrix.md)

**You are a maintainer proposing a change to `spec.md` or `constitution.md`.**

1. [`governance/amendment-process.md`](governance/amendment-process.md)
2. [`governance/versioning.md`](governance/versioning.md)
3. [`governance/sync-impact-reports.md`](governance/sync-impact-reports.md)

## What's deliberately *not* here

The seed README §"What the seed gives you, and what it does not" lists artifacts the **adopter** authors, not the seed:

- Detection rule corpus content.
- Cartographer document templates.
- Triager investigation procedure.
- Reporter writeup template & severity rubric.
- Hard-rules block beyond FR-111 minimums.

`docs/` does not provide these and never will. They are organization- and target-specific by definition.

Also out of scope:

- API references — there is no API.
- Installation guides — there is nothing to install.
- Restatements of FRs or principles — `docs/` cites; it does not normatively restate.

## Conventions for `docs/` content

When contributing here:

- **Cite, do not duplicate.** Link to a spec section or FR rather than restating it. If the spec is unclear, fix the spec.
- **Plain English first.** Diagrams second. Tables for matrices.
- **Mark the audience** at the top of each file (operator? reviewer? platform engineer?).
- **No prescription.** This is a seed; an adopter's stack will differ. Provide options and decision criteria, not mandates.
- **No new requirements.** If a doc here would impose a new MUST/SHOULD/MAY, the requirement belongs in `spec.md` or `constitution.md`, not in `docs/`.

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for general contribution rules.
