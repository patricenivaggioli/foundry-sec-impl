# Budget & Stop Conditions

**Audience:** a platform engineer implementing the budget governor ([`spec.md` §9.3](../../spec.md#93-budget)) and yield-gated auto-stop ([`spec.md` §9.4](../../spec.md#94-yield-auto-stop)) without misimplementing [Principle VI](../../constitution.md#vi-coverage-before-yield).

The conjunction "yield low AND coverage complete AND minimum runtime AND trailing window full" is the only correct auto-stop condition. This page is the worked-example companion to that conjunction.

---

## Budget tracking (§9.3)

### Required signals

The Orchestrator must track and surface:

- [ ] Cumulative LLM spend across all runs of an evaluation, in currency.
- [ ] Cumulative wall-clock runtime across all runs.
- [ ] Per-call cost attribution (FR-113), including which fraction is provider-reported vs estimated.

### Cost attribution

For every model call, record:

- Role (`detector`, `triager`, etc.).
- Tool name (if applicable).
- Provider (in case you have multiple — though Principle V cautions against multi-provider abstraction).
- Token count (input, output).
- Reported cost OR estimated cost from token rates.
- Whether reported or estimated.

The "fraction estimated" surfacing requirement (FR-113) exists because internal estimates drift from provider invoices. Surfacing the fraction lets operators sanity-check.

### Budget caps

- [ ] Cap configurable for both spend and runtime ([FR-112](../../spec.md#93-budget)).
- [ ] Default unset (unlimited) ([FR-114](../../spec.md#93-budget)).
- [ ] Pre-flight warning when both are unset ([FR-114](../../spec.md#93-budget)).
- [ ] Hard halt when either is exceeded.

### Refusing a re-run after a hit cap

[FR-011](../../spec.md#51-orchestrator): the Orchestrator MUST refuse to start a new evaluation run if a previous run hit a hard budget cap and the cap has not been raised. The error message must say which cap and how to reset.

This is to prevent the operator from blindly restarting a runaway run.

---

## Yield definition (§9.4)

[FR-115](../../spec.md#94-yield-auto-stop): trailing yield = severity-weighted, exploited-multiplied confirmed findings divided by spend, over a trailing spend window.

```
yield(t) = ΣᵢweightedSeverity(findingᵢ) × exploitedMultiplier(findingᵢ)
                                  ÷
                          spend in last W
```

Where:

- The sum runs over confirmed findings whose `true-positive` confirmation timestamp falls in the trailing window.
- `weightedSeverity` follows a geometric scale (FR-117 rationale): roughly 3.15× per tier, calibrated against multi-year bug-bounty payout ratios.
- `exploitedMultiplier` is 2× for findings with `exploited=true`.

### Worked example: a five-tier severity scheme

| Tier | Weight (≈3.15× per tier) |
|---|---|
| Critical | 100 |
| High | 32 |
| Medium | 10 |
| Low | 3 |
| Informational | 1 |

(`exploited` doubles the weight at any tier.)

A trailing window of $1,000 spend that contains:

- 1 Critical, exploited
- 2 High
- 1 Medium

Yields:

```
yield = (100 × 2 + 32 × 2 + 10) / 1000
      = 274 / 1000
      = 0.274
```

The threshold is operator-set ([FR-117](../../spec.md#94-yield-auto-stop)). If the operator's threshold is 0.05, this evaluation is well above it and should not auto-stop.

---

## Auto-stop conjunction (§9.4 / FR-116)

The Orchestrator halts only when **all** of the following hold:

| Condition | Source | Why |
|---|---|---|
| (a) At least one full trailing window of spend has accumulated. | Budget governor. | Without this, the metric is noise. |
| (b) Configured minimum runtime has elapsed. | Budget governor. | Without this, an early dry spell kills a young evaluation. |
| (c) Coverage-complete flag is set. | Coverage-Guide ([§5.7](../../spec.md#57-coverage-guide)). | Without this, "we found nothing in the first six hours" stops the run before the work was done. |
| (d) Trailing yield falls below the operator-set threshold. | Computed continuously. | The actual "we appear to be done" signal. |

### Worked example: stop, do not stop

#### Scenario 1: stop

Six hours into an evaluation. Coverage-Guide has set the coverage-complete flag (every checklist item attempted). Trailing window is full. Yield over the last $200 of spend is 0.02. Operator threshold is 0.05.

- (a) ✓ trailing window full.
- (b) ✓ 6h > minimum.
- (c) ✓ coverage-complete.
- (d) ✓ yield 0.02 < threshold 0.05.

**Auto-stop fires.** Honest done signal: we looked everywhere and the rate of new findings has flatlined.

#### Scenario 2: do not stop

Two hours into an evaluation. Trailing yield is 0.01 (very low). Coverage flag is *not* set (Detector and exploratory roles have not yet attempted half the targeted areas).

- (a) Maybe.
- (b) Probably ✓ (depends on minimum runtime configuration).
- (c) ✗ coverage not complete.
- (d) ✓ yield below threshold.

**Auto-stop does not fire.** Stopping here would mean ending an evaluation that has not yet done the requested work — exactly the failure Principle VI prevents.

#### Scenario 3: nearly there

Eight hours in. Yield 0.04 (just under threshold). Coverage 95% complete (a few areas still being attempted). Trailing window full.

- (a) ✓
- (b) ✓
- (c) ✗ coverage not yet complete (95% ≠ 100%).
- (d) ✓.

**Auto-stop does not fire.** The remaining 5% of coverage work continues; if yield rises above threshold during that work, condition (d) flips and stop is averted naturally. If it does not, stop fires once coverage flag flips.

---

## Yield-window and minimum-runtime tuning

### Trailing window

The window must be wide enough that yield is not dominated by single findings, but narrow enough to track changes responsively.

- **Too narrow:** yield jumps wildly on each finding; auto-stop oscillates near the threshold.
- **Too wide:** yield smooths; auto-stop fires late or never.

Reasonable default: $50–$500 of spend (one or two hours of full-fleet operation). Tune per target.

### Minimum runtime

The minimum runtime gate prevents auto-stop from firing on the first hour, when nothing has had time to ramp up.

Reasonable default: 30 minutes for small targets; 2+ hours for large targets. Tune per target.

### Severity weights

[FR-117](../../spec.md#94-yield-auto-stop) is explicit: weights should track the relative real-world value of findings at each tier.

- Geometric scale (constant ratio, ~3.15× per tier per the seed authors).
- 2× multiplier for `exploited` (reflects higher reviewer trust per [Principle VII](../../constitution.md#vii-exploited-means-demonstrated)).
- **Do not** default to a linear scale (1, 2, 3, 4, 5). Linear scales let low-severity volume dominate yield, which is wrong economically.

---

## Coverage-complete: what "coverage" means

The coverage flag is set by the Coverage-Guide ([§5.7](../../spec.md#57-coverage-guide)) based on the substrate's actual contents — every checklist item has been credibly attempted. Specifically:

- It does NOT mean "no bugs remain" (no system can know that).
- It DOES mean "the (area × technique) checklist the operator configured has each cell attempted by some agent".
- It is computed from the coverage log ([FR-046](../../spec.md#54-detector)), which is append-only.

Forbidden:

- Setting the flag based on agent claims that "this area is covered" — those are advisory ([Principle X](../../constitution.md#x-the-operator-outranks-every-agent), [FR-102](../../spec.md#83-inter-agent-communication)).
- Setting the flag manually to satisfy auto-stop.
- Inferring coverage from yield ("yield is low therefore coverage must be done") — that is exactly the inversion Principle VI prevents.

---

## Anti-patterns

| Pattern | Why it fails |
|---|---|
| Auto-stop on yield alone. | Fires on the first dry spell; kills young evaluations. |
| Auto-stop on runtime alone. | Says nothing about whether the work was done. |
| Setting coverage-complete to suppress auto-stop. | Defeats the conjunction; reproduces the failure Principle VI exists for. |
| Linear severity scale. | Low-severity volume dominates yield economically. |
| Per-call cost without role attribution. | Cannot identify where spend is going (FR-123 violated). |
| Pre-throttling LLM calls below provider limit "to control budget". | Forbidden — Principle V. Use the budget cap, not the rate cap, to control spend. |

## See also

- [`observability-checklist.md`](observability-checklist.md) — surfacing yield, coverage, and budget on the dashboard.
- [`sandbox-patterns.md`](sandbox-patterns.md) — sandbox patterns; budget and sandbox are independent concerns.
- [`../architecture/role-interactions.md#3-coverage-guide-feedback-loop`](../architecture/role-interactions.md#3-coverage-guide-feedback-loop) — the Coverage-Guide flow.
- [`../principles/anti-patterns.md#vi-coverage-before-yield`](../principles/anti-patterns.md#vi-coverage-before-yield) — failure modes when the conjunction is dropped.
- [`../../spec.md#94-yield-auto-stop`](../../spec.md#94-yield-auto-stop) — canonical requirements.
