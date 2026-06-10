# Worked Example: The Evidence Gate

**Audience:** anyone needing to see [`spec.md` §7.3](../../spec.md#73-evidence-gate) applied to concrete findings. Especially Triagers and Validators.

This page walks three findings through the evidence gate. One passes. One is demoted to `needs-review`. One is rejected. All three are fictional but representative of patterns the seed authors saw repeatedly.

The gate, restated: a `true-positive` MUST carry citations for **reachability**, **trust boundary**, and **impact**, and every citation MUST be mechanically verified to resolve to real code at verdict time ([FR-087, FR-088](../../spec.md#73-evidence-gate)).

---

## Finding A: passes the gate

### The candidate

The Detector flags `app/routes/admin.py:handle_export()` for SQL injection (CWE-89). The function ends with:

```python
def handle_export(request):
    user_id = request.args.get("user_id")
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cursor.fetchall()
```

### What the Triager produces

A `true-positive` verdict with three citations:

| Leg | Citation | Resolves? |
|---|---|---|
| Reachability | `app/routes/admin.py:handle_export()` is registered to route `/admin/export` in `app/__init__.py:42`. The route requires authentication, but session cookies are issued to any logged-in user. | yes |
| Trust boundary | `request.args.get("user_id")` is read directly from query string at `app/routes/admin.py:handle_export():2`. No validation, sanitization, or parameterization is applied before string interpolation into SQL at line 3. | yes |
| Impact | `cursor.execute()` at `app/routes/admin.py:handle_export():3` uses string interpolation, allowing arbitrary SQL. The DB user has read access to all tables in the application schema (verified via `app/db/conn.py:CONNECTION_DSN`), so a crafted `user_id` exfiltrates any user record. | yes |

### Mechanical check

The evidence-gate citation check confirms each cited line resolves to real code in the target. All three resolve. The verdict stands as `true-positive`.

If the testbed is configured, the Validator may further attempt independent reproduction. On successful reproduction of the headline impact ("read another user's record"), `exploited=true` is set ([FR-089](../../spec.md#74-exploited), [Principle VII](../../constitution.md#vii-exploited-means-demonstrated)).

### What this teaches

- Three legs, each citable, each resolving.
- The citations are specific (file, function, line) and verifiable, not prose-ish.
- The impact leg names a concrete consequence and traces *why* it follows from the cited code.

---

## Finding B: demoted to `needs-review`

### The candidate

The Detector flags `services/payments/process.py:handle_callback()` for IDOR (CWE-639). The function:

```python
def handle_callback(request):
    payment_id = request.json["payment_id"]
    payment = db.payments.get(payment_id)
    return jsonify(payment.to_dict())
```

### What the Triager initially produces

A `true-positive` verdict with three citations:

| Leg | Citation |
|---|---|
| Reachability | `services/payments/process.py:handle_callback()` is registered at `services/payments/__init__.py:31`. |
| Trust boundary | `request.json["payment_id"]` is read at `services/payments/process.py:handle_callback():2` without authorization check that the caller owns this payment. |
| Impact | `payment.to_dict()` returns full payment record, exposing other users' payment data. |

### Mechanical check

The evidence-gate citation resolver checks:

- `services/payments/process.py:handle_callback()` — **resolves**.
- `services/payments/__init__.py:31` — **does not resolve**. The file exists; line 31 is inside an unrelated function. The actual route registration is at `services/payments/__init__.py:54`.

By [FR-088](../../spec.md#73-evidence-gate), a citation that does not resolve demotes the verdict.

### Result

Verdict demoted to `needs-review`. The finding stays in the internal store; it does not surface to the issue tracker (because `needs-review` does not surface for Acme — see [`example-clarification.md`](example-clarification.md) round 1 policy answers, or per your own FR-057 clarification).

A re-triage with a corrected reachability citation could promote the verdict back to `true-positive`. Until then, the gate has done its job: prevented an under-evidenced claim from reaching reviewers.

### What this teaches

- The model's *argument* may be sound and the bug may be real, *and yet* the verdict is demoted because a citation did not resolve.
- This is not pedantry. It is the structural protection [Principle I](../../constitution.md#i-evidence-over-assertion) provides against fluent fabrication. The mechanical check fires regardless of how convincing the prose is.
- A re-triage corrects this; nothing about the bug being real is lost.

---

## Finding C: rejected

### The candidate

The Detector flags `lib/utils/format.py:safe_join()` for path traversal (CWE-22). The function:

```python
def safe_join(base, untrusted_path):
    base_path = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base_path, untrusted_path))
    if os.path.commonpath([base_path, candidate]) != base_path:
        raise ValueError("Path traversal attempt")
    return candidate
```

The Detector's hypothesis: `os.path.join` does not strip leading slashes; `untrusted_path` of `/etc/passwd` reaches the join, and `realpath` resolves it.

### What the Triager finds

The Triager investigates and concludes the function is **correctly implemented**:

- `os.path.join` does drop earlier components when given an absolute path (`/etc/passwd` becomes the entire result).
- `realpath` then resolves it.
- The `commonpath([base_path, candidate]) != base_path` check then rejects it because `/etc/passwd` is outside the allowed base directory.
- A `ValueError` is raised.

The candidate is a false-positive. The Triager records:

- Verdict: `false-positive`.
- Reasoning: "Detector hypothesis is incorrect; `commonpath` containment after `realpath` is precisely the right structure to defeat traversal. Function is correct."

### Result

The finding is recorded in the internal store with `false-positive` verdict and reasoning ([FR-086](../../spec.md#71-states)). It does not surface anywhere. On a re-run, the same fingerprint is recognized and the prior false-positive verdict is reused unless evidence has changed.

### What this teaches

- The Triager's job includes *rejecting* findings the Detector produced, with reasoning that future re-runs (and reviewers asking "did you consider this?") can consult.
- Rejection is not a failure of the system; it is the [Principle II](../../constitution.md#ii-surface-only-what-survives) machinery working: the noise stayed in the internal store.
- The reasoning is preserved precisely so a future reviewer or future re-run does not re-debate it from scratch.

---

## Cross-cutting observations

### Why mechanical resolution matters

In Finding B, the Triager's argument was largely correct. The line-number citation was the only fault. The system demoted the verdict anyway. *That is the point.* If the system trusts arguments to be self-checking when they "look right," it is back to trusting model confidence — and back to the failure mode [Principle I](../../constitution.md#i-evidence-over-assertion) was added to prevent.

### Why rejected findings are kept

In Finding C, the reasoning is preserved with the rejected finding. This means:

- A reviewer asking the Orchestrator "did you ever look at `safe_join`?" gets a citable answer ([FR-013](../../spec.md#51-orchestrator)).
- A re-run after a code change recognizes the same fingerprint and skips re-debating the unchanged function.
- A future Triager who suspects the function *is* vulnerable can examine the prior reasoning and either confirm it or counter it.

### What `exploited` looks like, and what it does not

In Finding A, the Validator may set `exploited` after independent testbed reproduction. It is **not** set:

- Because the Triager believes the bug is real.
- Because a debugger reproduction succeeded but no testbed was available.
- Because a "similar finding elsewhere was exploited."
- By the same agent that wrote the proof-of-concept payload.

[Principle VII](../../constitution.md#vii-exploited-means-demonstrated) and [FR-089](../../spec.md#74-exploited) are explicit on this.

## See also

- [`../architecture/finding-lifecycle.md`](../architecture/finding-lifecycle.md) — the state machine these findings traverse.
- [`../principles/anti-patterns.md#i-evidence-over-assertion`](../principles/anti-patterns.md#i-evidence-over-assertion) — failure modes the gate is structured to prevent.
- [`example-detection-rule.md`](example-detection-rule.md) — a CodeGuard rule that might fire on Finding A.
- [`example-clarification.md`](example-clarification.md) — Acme Bank's clarification choices that determine `needs-review` surfacing.
