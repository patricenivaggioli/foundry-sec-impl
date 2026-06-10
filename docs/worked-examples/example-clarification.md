# Worked Example: Clarification

**Audience:** an operator about to run `/speckit.clarify` for the first time and wanting to see one all the way through.

This is a fictional walkthrough. "Acme Bank" is not a real organization; the answers below are illustrative, not recommended.

The example shows three rounds of clarify ↔ specify, mirroring the README's [Step 6](../../README.md#step-6-iterate-clarify-and-specify-until-they-converge) warning that specify routinely introduces new underspecification.

---

## Round 1: clarify on the seed

Acme Bank has just copied `spec.md` into `specs/001-foundry/`. The first `/speckit.clarify` walks through the markers indexed in [`spec.md` §15](../../spec.md#15-open-questions-index).

### Identity & scope

> **Agent:** What is this system's name?

**Operator (Acme):** "Spectre. Spectre is the system."

> **Agent:** Does the assumption "authorized eval with source access" hold?

**Operator:** "Yes. Spectre evaluates first-party services Acme owns and operates."

> **Agent:** Should any of the eight core roles be merged, split, or omitted?

**Operator:** "We will not merge or split. We will run all eight."

### Integration choices

> **Agent:** Which version control & issue tracker?

**Operator:** "GitHub Enterprise Server, with Issues enabled per repo. Service account `acme-spectre-bot`."

> **Agent:** Which LLM provider?

**Operator:** "Anthropic Claude via our internal LLM gateway, which forwards rate-limit headers untouched."

> **Agent:** Which datastore?

**Operator:** "PostgreSQL 16 in a managed RDS instance, transactional updates for the finding store."

> **Agent:** Vector search?

**Operator:** "Yes. Postgres + pgvector for the seed run. FR-023 is in scope."

> **Agent:** Deployment topology?

**Operator:** "Single Kubernetes cluster, one StatefulSet per agent role, agents scaled per role-count config."

> **Agent:** Container / isolation runtime?

**Operator:** "We will use gVisor. We accept that the gVisor sandbox is the Principle IX boundary, not a Docker network policy."

> **Agent:** Authentication model?

**Operator:** "OIDC against our IdP. Service accounts per role with workload identity."

> **Agent:** Agent harness?

**Operator:** "Claude Code, vendored into our Spectre image, customized only for tool gating per role."

> **Agent:** Severity & classification scheme?

**Operator:** "CVSS v4.0 with Acme's enterprise vector profile."

> **Agent:** Compliance mapping?

**Operator:** "Map to PCI-DSS where applicable; ignore for non-payment services."

> **Agent:** Downstream export?

**Operator:** "JSON to S3 nightly, in addition to the issue tracker."

> **Agent:** Testbed?

**Operator:** "Yes; an isolated VPC reachable only from Validator agents."

### Policy choices

> **Agent:** Should `needs-review` findings surface?

**Operator:** "No. Internal only. Operators query the substrate if they need to see them."

> **Agent:** Label naming?

**Operator:** "`spectre/`-prefixed: `spectre/triaged-true-positive`, `spectre/exploited`, `spectre/severity-critical`, etc."

### Extension scope

> **Agent:** Deep-Tester?
> **Operator:** "No."
> **Agent:** Variant-Hunter?
> **Operator:** "No."
> **Agent:** Attack-Mapper?
> **Operator:** "No."
> **Agent:** Remediator?
> **Operator:** "No."
> **Agent:** Self-Improver?
> **Operator:** "No, not for the seed run."

### End-of-round summary

The agent appends a Clarifications log to `spec.md` and reports: "All `[NEEDS CLARIFICATION]` markers resolved."

---

## Round 1: specify

```
/speckit.specify
```

Specify hardens the spec:

- Renumbers FRs contiguously now that FR-023 is *kept* (vector search yes), and renumbers FRs that depended on extension roles being absent.
- Removes the §6.1–§6.5 normative content (extensions all "no") but keeps the section as a placeholder describing why each is currently disabled.
- Sets status from `SEED` to `DRAFT`.

The status block at the top now reads:

```
| Version | 0.2.0 (per Acme) |
| Status  | DRAFT |
| Applies to | Spectre v1 |
```

---

## Round 2: clarify (the surprise)

Acme runs `/speckit.clarify` again. The agent reports markers exist:

> **Agent:** §11.1 mentions GitHub Enterprise Server. Spectre's Reporter writes issues, but the GHES instance Acme uses is at a custom hostname behind their VPN. What is the API endpoint?

**Operator:** "https://github.acme-internal.example/api/v3"

> **Agent:** §10 (Observability) says the dashboard is delivered as a web UI served by the Orchestrator, terminal UI, static page, or panels on an existing observability stack. Which?

**Operator:** "Panels on Acme's existing Grafana stack. Spectre exposes Prometheus metrics and writes structured logs to Loki."

> **Agent:** §9.1 marker on sandbox enforcement: gateway sidecar, host firewall, security groups, network policy, or other?

**Operator:** "AWS security groups + Kubernetes NetworkPolicy + the gVisor-imposed kernel boundary. Egress is filtered at the cloud SG layer."

These markers were not in the seed `spec.md` §15 index — specify *introduced* them when expanding §11.1 / §9.1 / §10 with Acme's specific answers. This is exactly the [README Step 6](../../README.md#step-6-iterate-clarify-and-specify-until-they-converge) phenomenon.

---

## Round 2: specify

Specify expands the integration sections with Acme's concrete answers and re-runs the constitution conformance check. It reports no conflicts.

The Clarifications log now has two entries: round 1 (initial), round 2 (cascaded).

---

## Round 3: clarify (the convergence)

Acme runs `/speckit.clarify`. The agent reports: "No outstanding markers."

Acme then performs a manual read of `spec.md`. The reading pass is a deliberate part of the workflow — tools assist, they do not certify. Acme finds:

> §5.4 still uses the seed phrase "the chosen LLM provider" in one paragraph that was not regenerated.

The operator edits that paragraph to read "Anthropic Claude" directly, and runs `/speckit.clarify` once more. The agent confirms no markers and the manual read finds nothing.

---

## What this teaches

1. **The first clarify is the hardest.** Most decisions are made there.
2. **Specify-introduced markers are normal.** Acme answered "GitHub Enterprise" in round 1; specify expanded the integration section and surfaced "what is the endpoint" in round 2. This is how the workflow finds things you did not realize you needed to decide.
3. **Two or three rounds is normal.** Acme converged in three.
4. **The manual read pass matters.** A clean clarify does not certify a clean spec. Read the result.
5. **"No to extensions" is a real answer.** Acme deliberately said no to all five §6 extensions for the first build. They will revisit each per [`../adoption/extension-roles-when.md`](../adoption/extension-roles-when.md) once the core fleet is producing trusted findings.

## What Acme will *not* do

- Set `exploited` from prose ([Principle VII](../../constitution.md#vii-exploited-means-demonstrated)).
- Cap LLM calls below the gateway's actual rate ([Principle V](../../constitution.md#v-the-provider-is-the-rate-arbiter)).
- Use wall-clock timeouts to reclaim claims ([Principle III](../../constitution.md#iii-liveness-by-heartbeat-never-by-clock)).
- Surface every Detector candidate to the GHES tracker ([Principle II](../../constitution.md#ii-surface-only-what-survives)).

These are not "best practices we adopted"; they are constitutional. Acme's `plan.md` will be checked against them by `/speckit.analyze` on every invocation.

## See also

- [`example-detection-rule.md`](example-detection-rule.md) — a CodeGuard rule mapped to FR-037.
- [`example-evidence-gate.md`](example-evidence-gate.md) — three findings walked through the gate.
- [`../adoption/clarification-playbook.md`](../adoption/clarification-playbook.md) — marker-by-marker guidance.
- [`../adoption/integration-decisions.md`](../adoption/integration-decisions.md) — decision frameworks for §11 surfaces.
