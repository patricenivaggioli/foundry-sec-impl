# When to enable each extension role

**Audience:** an operator considering whether to turn on an extension role from [`spec.md` §6](../../spec.md#6-extension-roles).

The README is explicit:

> **Recommended: no to all five for your first build.** Get the eight core roles producing trustworthy findings, then revisit.

This document gives the *signals* that tell you "now is the time" for each extension. If the signals are not present, the answer remains no.

## Universal preconditions

Before considering any extension, verify the eight core roles are healthy:

- [ ] Detector → Triager → Validator → Reporter pipeline runs end to end without operator intervention.
- [ ] False-positive rate at the issue tracker is steady and acceptable to your reviewers.
- [ ] Coverage-Guide reports complete coverage on at least one target.
- [ ] Operator-help-request handling (FR-015) works.
- [ ] You have at least one finding with `exploited=true` (or you have explicitly accepted the no-testbed limitation).

If any of those is unchecked, do **not** enable extensions. The extensions amplify both signal and noise; amplifying noise is worse.

---

## §6.1 Deep-Tester — turn on when you see…

A backlog of findings stuck at "evidence is plausible, but we cannot confirm impact in the testbed without a custom payload." Deep-Tester invests in building those payloads.

**Preconditions:**

- A stable testbed reachable from a sandboxed Validator-class agent.
- A Reporter who pays attention to `exploited=true` and treats it as the highest-trust label.
- At least one example of a finding that *would* be exploited if a payload existed.

**Anti-signals (do not turn on):**

- Testbed is intermittent or shared with other systems.
- Operators rarely ask "can you prove this is exploitable?".
- Reviewers do not yet trust `true-positive` evidence.

## §6.2 Variant-Hunter — turn on when you see…

The same vulnerability class appearing in different functions / modules across runs, and you want similarity-driven hunting rather than another rule.

**Preconditions:**

- Vector store deployed and Indexer FR-023 (semantic embeddings) is producing usable results.
- A confirmed corpus of true-positive findings to seed similarity queries.
- The rule corpus has been examined and the bug class genuinely cannot be expressed as a rule (otherwise: improve the rule).

**Anti-signals:**

- "We have not enabled vector search yet."
- "We have only one true-positive."
- The bug class is well-defined and expressible as a CodeGuard rule — write the rule instead.

## §6.3 Attack-Mapper — turn on when you see…

Reviewers asking "could finding A and finding B chain?" repeatedly, or the system has been operating for at least two evaluation cycles and you want graph-based reasoning over historical findings.

**Preconditions:**

- A graph store (or you are willing to back attack maps with your existing datastore).
- A node-id scheme that is stable across runs (don't use line numbers — Principle VIII).
- Documented "by-design" edges (intentional flows the Mapper should not flag).

**Anti-signals:**

- First-build.
- Findings are mostly local (single-function bugs).
- No clear graph-reasoning question your operators are asking.

## §6.4 Remediator — turn on when you see…

Reporter output is high-quality enough that the natural next ask is "and please propose a fix." Remediator drafts patches.

**Preconditions:**

- A code-review process that gates AI-suggested changes (a human reviewer always merges).
- The Reporter writeup includes enough specificity that a fix proposal is bounded.
- You have a way to test the proposed fix (CI, unit tests, the testbed).

**Anti-signals:**

- Reporter output still varies in quality.
- "We'll auto-merge if the model says it's safe." Forbidden — Principle X (Operator Outranks).
- No CI / no test harness.

## §6.5 Self-Improver — turn on when you see…

The rule corpus has measurable, documented gaps and you want the system to propose new rules from rule-gap entries (FR-042).

**Preconditions:**

- Rule-gap recording (FR-042) has been operating in the Triager for at least a quarter, producing a corpus of gaps.
- A human reviewer owns rule-corpus PRs (Self-Improver proposes; humans merge).
- The CodeGuard rule format (or your equivalent) is stable.

**Anti-signals:**

- No rule-gap entries yet recorded.
- "We'll let it auto-merge to keep up with discovery." Forbidden — Principle X again.
- Rule corpus is itself unstable / under heavy churn.

---

## How to turn one on (procedure)

1. Re-run `/speckit.clarify` and answer "yes" only to the extension you are enabling.
2. Run `/speckit.specify`. New FRs will be authored from the §6 sketch. Almost all of them will carry their own `[NEEDS CLARIFICATION]` markers.
3. Re-clarify the new markers; re-specify; iterate until convergence (see [`quickstart.md`](quickstart.md) Step 6).
4. Run `/speckit.plan` and `/speckit.analyze`. The constitution check is the final gate.

## How to turn one off

If an extension is not paying off, disable it. The seed treats §6 as additive, not load-bearing — disabling an extension never breaks a core role.

## See also

- [`clarification-playbook.md`](clarification-playbook.md) — Group D table.
- [`../architecture/role-interactions.md`](../architecture/role-interactions.md) — how extensions plug into the core flow.
- [`../principles/anti-patterns.md`](../principles/anti-patterns.md) — what each extension must not do.
