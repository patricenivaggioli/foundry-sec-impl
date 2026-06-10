# Worked Example: A Detection Rule

**Audience:** an operator authoring rules for the Detector ([`spec.md` §5.4](../../spec.md#54-detector)) who wants to see one rule mapped to the FRs it satisfies and the lifecycle it participates in.

This page uses [CodeGuard](https://github.com/cosai-oasis/project-codeguard) format because that is the format the seed assumes. Adopt CodeGuard, fork it, or use it only as a reference for your own rule format — the seed does not require it.

---

## The rule

A simplified rule targeting shell-command calls with user-controlled input in Python:

```yaml
id: codeguard-py-shell-injection-from-flask
description: |
  Detect call to subprocess.run / subprocess.call / os.system / etc. where
  the command argument flows from a Flask request without sanitization.
languages: [python]
severity: high
weakness_class: CWE-78
applies_to:
  - functions calling subprocess.{run,call,Popen} with shell=True
  - or os.system / os.popen
trigger_when:
  - the command argument is reachable from a Flask route handler argument
  - and there is no structured argv form, documented allowlist, or other
    shell-free command construction
example_positive: |
  @app.route("/run")
  def run():
      cmd = request.args.get("cmd")
      subprocess.run(cmd, shell=True)
example_negative: |
  @app.route("/run")
  def run():
      cmd = request.args.get("cmd")
      subprocess.run(["/bin/echo", cmd], shell=False)
```

This is a sketch. A real CodeGuard rule has more structure (test cases, generation hints, etc.); see the [CodeGuard repo](https://github.com/cosai-oasis/project-codeguard) for the actual schema.

## How the rule fits the Detector's contract

| FR | What the rule provides |
|---|---|
| [FR-037](../../spec.md#54-detector) (rule-based code analysis) | The rule is the unit applied per function. |
| [FR-041](../../spec.md#54-detector) (versioned, independent corpus) | The rule lives in the rule repository, versioned independently of the Detector code. |
| [FR-043](../../spec.md#54-detector) (per-finding metadata) | Each candidate the rule produces records location, vulnerability class, description, and the technique ("rule: codeguard-py-shell-injection-from-flask"). |
| [FR-044](../../spec.md#54-detector) (no direct issue tracker writes) | The rule does not bypass this; the Detector does the writing, and only to the internal store. |
| [FR-045](../../spec.md#54-detector) (dedup by fingerprint) | The Detector dedupes candidates from this rule against the existing finding store before writing. |
| [FR-090](../../spec.md#75-fingerprint) (fingerprint stable under edit) | The fingerprint is `(path, function_name, "CWE-78")`. Rule id is *not* part of the fingerprint — multiple rules can fire on the same fingerprint. |

## What happens when the rule fires

1. **Sweep** ([FR-037](../../spec.md#54-detector)). The Detector applies the rule to every Python function in scope, with the function body and its caller/callee context from the Indexer.
2. **Candidate written** ([FR-043, FR-044](../../spec.md#54-detector)). If the rule fires, the Detector writes a candidate finding to the internal store, deduped by fingerprint.
3. **Triage** ([§5.5](../../spec.md#55-triager)). The Triager investigates. The rule's metadata (which rule, what the LLM-evaluated check returned) is part of the context.
4. **Evidence gate** ([§7.3](../../spec.md#73-evidence-gate)). If the Triager promotes to `true-positive`, the verdict carries citations for reachability, trust boundary, and impact, mechanically resolved.
5. **Validation** ([§5.6](../../spec.md#56-validator)). If a testbed exists, the Validator may attempt independent reproduction; on success, sets `exploited` ([FR-089](../../spec.md#74-exploited)).
6. **Report** ([§5.8](../../spec.md#58-reporter)). The Reporter writes (or updates, keyed on fingerprint per [FR-090](../../spec.md#75-fingerprint)) an issue in the tracker.

## What happens when *no* rule fires but exploration finds it

This is the rule-gap case ([FR-042](../../spec.md#54-detector)).

Imagine an exploratory agent ([FR-040](../../spec.md#54-detector)) finds a similar shell injection in a different framework (FastAPI, not Flask). The rule above would not fire, because it explicitly applies to Flask routes. The exploratory finding is triaged, promoted, validated.

At promotion, the Triager checks: did any rule produce an equivalent candidate? The answer is no.

[FR-042](../../spec.md#54-detector) MUST be invoked: the Triager records a rule-gap entry capturing:

- Reference to the finding.
- Vulnerability class: CWE-78 (OS Command Injection).
- The pattern existing rules failed to match: "FastAPI route handlers".

A human (or, with §6.5 enabled, the Self-Improver) reads the rule-gap entry and:

- Either generalizes the rule to "any web framework route handler" with a list of frameworks, or
- Authors a sibling rule `codeguard-py-shell-injection-from-fastapi`.

The corpus grows. Future evaluations on FastAPI targets catch the class on the first pass.

This is the [rule-gap flywheel](../architecture/rule-gap-flywheel.md) in action.

## What the rule does *not* do

- It does not set `exploited`. That is the Validator's exclusive authority ([FR-089](../../spec.md#74-exploited), [Principle VII](../../constitution.md#vii-exploited-means-demonstrated)).
- It does not assign severity. The Reporter does that, against the operator's chosen rubric ([§11.9](../../spec.md#119-severity--classification-schemes)). The rule's `severity: high` is a *hint*; the Reporter applies its own rubric.
- It does not produce issues. Only the Reporter writes to the tracker ([FR-078–FR-080](../../spec.md#58-reporter)).
- It does not promote findings. Only the Triager assigns `true-positive` after the evidence gate and surfaces true positives via Reporter ([FR-052, FR-057](../../spec.md#55-triager)).
- It does not deduplicate. The Detector deduplicates against the finding store ([FR-045](../../spec.md#54-detector)).

These are not the rule's job. The rule is a single, focused signal; the rest of the system is the machinery that makes the signal valuable.

## Compounding value

Once landed, this rule:

- Runs against every future Python target Acme evaluates.
- Loads into the same CodeGuard rule set used by Acme's IDE-side coding assistant, where it warns developers writing `subprocess.run(cmd, shell=True)` against user input *before* the next evaluation.
- Improves further when its rule-gap descendants land.

This is the asymmetry the seed README highlights: detection effort compounds; exploratory effort does not (one finding ≈ one finding) unless its lessons are captured as rules.

## See also

- [`example-evidence-gate.md`](example-evidence-gate.md) — three findings walked through §7.3 (one might be from this rule).
- [`../architecture/rule-gap-flywheel.md`](../architecture/rule-gap-flywheel.md) — the diagram and narrative.
- [`../adoption/extension-roles-when.md`](../adoption/extension-roles-when.md) — when to enable Self-Improver to automate rule-gap → rule.
- [CodeGuard schema and examples](https://github.com/cosai-oasis/project-codeguard).
