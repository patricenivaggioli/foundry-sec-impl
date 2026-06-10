# Open Questions Checklist

**Audience:** an operator running `/speckit.clarify`, who wants a printable / tickable companion to [`spec.md` §15](../../spec.md#15-open-questions-index).

This is a checklist you can print, tape to a wall, and tick off in a conference room. The authoritative list lives in [`spec.md` §15](../../spec.md#15-open-questions-index); this is a checkable mirror.

If a question here is missing from the spec, **the spec is right** and this file needs regeneration.

## How to use it

- Group A (identity & scope) is mandatory and answered first.
- Group B (integration) is mandatory; "I do not know yet" is acceptable for first-pass and will be resurfaced during `/speckit.plan`.
- Group C (policy) is mandatory; use existing organizational conventions where possible.
- Group D (extension) — **the recommended answer for a first build is "no" to all five**.

For each question, mark:

- `[x]` answered — and record the answer in `spec.md`.
- `[ ]` not answered — must be answered before promoting `spec.md` from `SEED` to `DRAFT`.

For deeper guidance on each, see [`../adoption/clarification-playbook.md`](../adoption/clarification-playbook.md).

---

## Group A — Identity & scope

- [ ] **§0** — System name (the name *you* own, not "Foundry").
- [ ] **§1.5** — Does your use case match "authorized, source-available"?
- [ ] **§4.2** — Merge, split, or omit any of the eight core roles?
- [ ] **§5.1** — Orchestrator: long-running service or per-command CLI?

## Group B — Integration choices

### Knowledge layer

- [ ] **§5.2** — Indexer: which languages?
- [ ] **§5.2 / §11.4** — Use semantic code search / a vector store?
- [ ] **§5.3** — Cartographer: gate fleet spawn (no / yes / soft-gate Triager only)?
- [ ] **§5.3** — Cartographer: single agent, document-per-pass pipeline, or wrap an existing tool?

### Detection & triage

- [ ] **§5.4** — Detector: which of the four techniques are in scope?
- [ ] **§5.4** — Detection rule corpus: per-evaluation, org-wide library, external seed, or combination? Where stored/versioned?
- [ ] **§5.5** — Triager: fixed procedure or open tool-use loop?
- [ ] **§5.5 (ref. §7.2)** — Surface `needs-review` to humans?

### Validation & reporting

- [ ] **§5.6 / §11.12** — Testbed: always, sometimes, or never?
- [ ] **§5.6** — PoC artifact header policy.
- [ ] **§5.8 / §11.9** — Weakness taxonomy (CWE or other)?
- [ ] **§5.8 / §11.9** — Severity scheme (CVSS, qualitative, custom)?
- [ ] **§5.8** — Code permalink construction & reader access.
- [ ] **§5.8 / §11.11** — Downstream defect-tracker export?

### Lifecycle & infrastructure

- [ ] **§7.6** — Concrete label names/colors.
- [ ] **§9.1 / §11.6** — Sandbox enforcement mechanism (gateway, host firewall, security groups, network policy, runtime isolation, etc.).
- [ ] **§10** — Dashboard delivery mechanism (web UI, terminal, static, panels on existing observability stack).
- [ ] **§11.1** — VCS host & issue tracker.
- [ ] **§11.2** — LLM provider, models, tiering.
- [ ] **§11.3** — Datastore.
- [ ] **§11.5** — Deployment topology; single- vs multi-tenant.
- [ ] **§11.7** — Authentication model to VCS/tracker.
- [ ] **§11.8** — Agent harness.
- [ ] **§11.10** — Compliance framework mapping.
- [ ] **§12** — Configuration file format.
- [ ] **§13 / NFR-003** — Multi-tenancy required?

## Group C — Policy choices

(Several are absorbed into Group B above — `needs-review` surfacing, label names, severity, taxonomy, compliance. Treat them as policy decisions even when their markers live in §11 or §7.)

## Group D — Extension scope (default: no)

- [ ] **§6.1** — Deep-Tester in scope?
- [ ] **§6.2** — Variant-Hunter in scope?
- [ ] **§6.3** — Attack-Mapper in scope?
- [ ] **§6.4** — Remediator in scope?
- [ ] **§6.5** — Self-Improver in scope?

For each "yes", expect `/speckit.specify` to author new FRs that carry their own markers — see [`../adoption/extension-roles-when.md`](../adoption/extension-roles-when.md).

---

## Convergence checks

Before promoting `spec.md` from `SEED` to `DRAFT`:

- [ ] Every Group A and Group B box ticked.
- [ ] Every Group D box ticked (yes or no, deliberately).
- [ ] `/speckit.clarify` reports no outstanding markers.
- [ ] Manual read of `spec.md` finds no template-language phrases ("the chosen X", "an appropriate Y").
- [ ] `/speckit.specify` has been run and reports no constitutional conflicts.

If all five are checked, the spec is ready for `/speckit.plan`.

## See also

- [`../adoption/clarification-playbook.md`](../adoption/clarification-playbook.md) — marker-by-marker guidance.
- [`../adoption/integration-decisions.md`](../adoption/integration-decisions.md) — decision frameworks for §11 surfaces.
- [`../adoption/extension-roles-when.md`](../adoption/extension-roles-when.md) — signals that justify §6 yes answers.
- [`../worked-examples/example-clarification.md`](../worked-examples/example-clarification.md) — fictional org walkthrough.
- [`../../spec.md#15-open-questions-index`](../../spec.md#15-open-questions-index) — the authoritative list.
