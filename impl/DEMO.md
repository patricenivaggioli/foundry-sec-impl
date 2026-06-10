# Foundry Sec — Red Team Demo Walkthrough

> Audience: red-team / offensive-security colleagues evaluating whether this
> architecture would be useful for their own assessments.
>
> Goal: in **~20 minutes** convince them that:
>   1. The pipeline finds real vulnerabilities, with **machine-checkable evidence**
>      (no fabricated citations possible).
>   2. The output is a **SARIF triage queue**, not a wall of LLM prose.
>   3. The architecture's invariants are enforced **at the data layer**, not by
>      prompt-engineering hope.
>
> Total time: ~20 min. No Mistral API key required (mock LLM ships with the demo).

---

## 0. Prereqs (one-time, ~3 min)

```bash
cd impl
docker compose -f deploy/compose.yml up -d           # Postgres
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]' -q
export FOUNDRY_DSN=postgresql://foundry:foundry@localhost:5432/foundry
foundry init-db --config configs/demo.yaml
```

Optional, for real LLM judgments:

```bash
export MISTRAL_API_KEY=sk-...
```

Without the key, every LLM call routes to a deterministic mock that produces
*structurally valid* outputs — good enough to demonstrate the pipeline shape;
not good enough to find real bugs in non-fixture code.

---

## Scenario 1 — "Find the planted bugs" (5 min)

**Pitch:** _"Run the pipeline against this small Flask app. It will find SQL
injection, command injection, insecure deserialization, and `eval()` — and it
will refuse to claim anything it cannot quote."_

```bash
foundry run --config configs/demo.yaml --output output
cat output/report.md
```

### What to point at

* **`output/findings.sarif`** — drop into VS Code's SARIF viewer or GitHub
  Advanced Security; this is the same format your existing tools emit.
* **Fingerprints** like `demo-r1|myapp/__init__.py|search_users|CWE-89`. Note
  that **line numbers are deliberately absent** (Principle VIII): the same bug
  re-detected after a refactor that shifted the line count keeps the same
  fingerprint. Try it: add a blank line at the top of `fixtures/vulnerable_app/myapp/__init__.py`,
  re-run, and confirm the fingerprint is unchanged.
* **Every "true-positive" finding has at least one `citations[]` entry** that
  is a verbatim substring of the function body. The `report.md` shows it
  inline as a fenced quote.

### Talk track

> "Every claim is backed by an excerpt the substrate verified against the
> indexed source. If the model fabricates an excerpt, the **database** rejects
> the INSERT — not a downstream review step. If the model then tries to assert
> a true-positive verdict with no citations, the UPDATE also fails. Watch."

---

## Scenario 2 — "The model lies; the substrate doesn't" (3 min)

This is the most important demo for a red-team audience. We'll directly attempt
to bypass the citation gate using `psql` and watch the DB refuse.

```bash
podman exec -it deploy-postgres-1 psql -U foundry
```

```sql
-- Pick any candidate finding from a recent evaluation.
SELECT id, path, symbol, vuln_class FROM findings ORDER BY created_at DESC LIMIT 1;
\gset
SELECT id FROM evaluations ORDER BY created_at DESC LIMIT 1;
\gset

-- Attempt 1: fabricate a citation.
INSERT INTO evidence_citations (finding_id, evaluation_id, cite_path, cite_symbol, quoted_excerpt)
VALUES (:'id', :'id', 'myapp/__init__.py', 'myapp.__init__.search_users',
        'DROP TABLE users; -- I made this up');
-- → ERROR: Citation rejected: excerpt does not appear in body of ...
```

```sql
-- Attempt 2: bypass the gate by setting verdict=true-positive without any citation.
-- (First, find a candidate with zero accepted citations.)
SELECT f.id FROM findings f
 LEFT JOIN evidence_citations c ON c.finding_id = f.id
 WHERE c.id IS NULL LIMIT 1;
\gset

UPDATE findings SET verdict='true-positive', survived_gate=true WHERE id = :'id';
-- → ERROR: Evidence gate: true-positive verdict requires >= 1 citation
```

### Talk track

> "Two prompt-engineering attacks bypassed by one constraint each. This is
> what we mean by 'integrity at the data layer'. A red-team operator using
> this output downstream can take `survived_gate = true` at face value because
> Postgres won't permit anything else."

---

## Scenario 3 — "Independent reproduction — Principle VII" (3 min)

The Validator pattern: a PoC author and a runner with **distinct identities**.
The DB CHECK constraint refuses to record an exploit if both are the same agent.

```bash
podman exec -it deploy-postgres-1 psql -U foundry
```

```sql
SELECT proof.finding_id,
       a1.role  AS poc_author_role,
       a2.role  AS runner_role,
       (a1.id = a2.id) AS same_identity_BLOCKED
  FROM exploit_proofs proof
  JOIN agents a1 ON a1.id = proof.poc_author_agent_id
  JOIN agents a2 ON a2.id = proof.runner_agent_id;
```

> Expected: `same_identity_BLOCKED` is always `false`. This is enforced by
> `CHECK (poc_author_agent_id <> runner_agent_id)` in the schema.

Attempt to subvert it:

```sql
INSERT INTO exploit_proofs (finding_id, evaluation_id, poc_author_agent_id, runner_agent_id, artifact_uri, observed_impact, sandbox_log_uri)
SELECT id, evaluation_id, claimed_by, claimed_by, '/tmp/x', 'fake', 'inline:none' FROM work_queue WHERE claimed_by IS NOT NULL LIMIT 1;
-- → ERROR: new row for relation "exploit_proofs" violates check constraint "exploit_independent_runner"
```

### Talk track

> "If a single rogue agent could draft and 'run' its own PoC, the entire
> Validator role collapses into theatre. The CHECK is a 12-character contract
> that this never happens — independent of how many model patches or
> instruction tweaks ship later."

---

## Scenario 4 — "Concurrent fleet, no double-work" (4 min)

Run two evaluators in parallel against the same target and watch the work
queue split atomically. This demonstrates Principle IV (`SELECT … FOR UPDATE
SKIP LOCKED`).

In terminal A:

```bash
foundry run --config configs/demo.yaml --output output-a &
```

In terminal B (immediately):

```bash
foundry run --config configs/demo.yaml --output output-b &
```

While both run, watch the substrate:

```bash
watch -n1 'podman exec deploy-postgres-1 psql -U foundry -c "
  SELECT a.role, COUNT(*) FILTER (WHERE w.state=\"claimed\") AS claimed,
                 COUNT(*) FILTER (WHERE w.state=\"done\")    AS done
    FROM work_queue w JOIN agents a ON a.id = w.claimed_by
   GROUP BY a.role ORDER BY a.role;"'
```

### Talk track

> "No two agents ever own the same task — `SKIP LOCKED` makes the work queue
> a multi-consumer broker without any orchestrator state-machine code. If a
> worker dies mid-task, the claim's TTL expires and another picks it up. We
> never reclaim by wall-clock task age — only on stale heartbeat (Principle III).
> That's why we don't get 'orphan' findings written twice."

---

## Scenario 5 — "Bring your own target" (5 min)

Point the pipeline at one of the red-team's own throwaway repos:

```bash
git clone https://github.com/your-team/sample-vuln-app /tmp/target
```

Edit `configs/redteam.yaml`:

```yaml
name: redteam-demo

substrate:
  dsn: ${env:FOUNDRY_DSN}

llm:
  provider: mistral
  strong_model: mistral-large-latest
  bulk_model: mistral-small-latest
  region: eu

target:
  path: /tmp/target
  revision: main

budget:
  tokens: 500_000
  wallclock_seconds: 1800

concurrency:
  detector: 4
  triager: 4

goals:
  attack_goals:
    - data_exfiltration
    - rce
    - auth_bypass
    - privilege_escalation
```

```bash
export MISTRAL_API_KEY=sk-...     # for real evaluation
foundry run --config configs/redteam.yaml --output output-redteam
```

### Discussion prompts for the red team

* **What rule corpus would you want?** The MVP ships 4 rules. Real use needs a
  curated CWE/CAPEC corpus — the corpus is just rows in `RULES` (see
  `foundry/agents/detector.py`). Would you import from Semgrep registry, or
  hand-author?
* **Validator sandbox.** The demo's "runner" doesn't actually execute the PoC
  — it asks the LLM to predict observed impact. In production this slot is
  filled by a Firecracker microVM (Principle IX). What testbed would you wire
  in for a Web target? An API target? A network device?
* **Override workflow.** When you disagree with a verdict, write to the
  `overrides` table — the report consumes it on next emit. Show:
  ```sql
  INSERT INTO overrides (evaluation_id, finding_id, override_verdict, reason, author)
  VALUES (..., ..., 'false-positive', 'unreachable from /api in prod', 'alice');
  ```

---

## Scenario 6 — "Inspect the trace" (post-demo)

Every LLM call, task transition, and citation acceptance/rejection is in
`session_logs`. This is the audit substrate — exactly what a red-team report
needs as appendix.

```sql
SELECT timestamp, role, event_type, payload->>'task_id' AS task,
       tokens_in, tokens_out
  FROM session_logs
 WHERE evaluation_id = (SELECT id FROM evaluations ORDER BY created_at DESC LIMIT 1)
 ORDER BY timestamp DESC LIMIT 50;
```

Pull a single finding's full trail:

```sql
SELECT timestamp, role, event_type, payload, tokens_in, tokens_out
  FROM session_logs
 WHERE finding_id = '<uuid>'
 ORDER BY timestamp;
```

> "Reproducibility for free: with `evaluation.config` (the YAML) +
> `target_revision` + the session_logs slice, you can re-run any single triage
> deterministically (with the mock client) or with any Mistral seed
> (real client)."

---

## Cheat-sheet for the demo presenter

| Question they'll ask | Answer |
|---|---|
| "How is this different from Semgrep + an LLM check?" | Semgrep is one of the Detector strategies. The architecture's value is downstream: the **citation gate**, the **independent Validator**, the **stable fingerprint**, the **multi-dimensional coverage state**. Those are absent in `tool + LLM` setups. |
| "What stops the LLM from hallucinating findings?" | Two layers: (a) the citation gate at insert time, (b) the evidence gate at verdict time. Both are SQL triggers. Show the `psql` attempts in Scenario 2. |
| "Can I bypass it by patching the agent code?" | You can patch the agent to skip emitting citations — and the verdict will be auto-demoted to `needs-context`. You can't patch the database without an admin role; that's a separate trust boundary. |
| "Is this fast?" | The fixture demo runs in ~20 s on mock; ~3-5 min with Mistral against a few-thousand-LOC target. Throughput scales linearly with `concurrency.detector` and `concurrency.triager` because the substrate is the only synchronization point. |
| "What's the failure mode?" | Stale heartbeat → claim reclaimed → another agent finishes the task. No work is lost. If the LLM is rate-limited, the fleet adapts (Principle V). If the pipeline crashes mid-eval, restart picks up wherever the queue left off (Principle XI). |
| "What's missing for production?" | Phase P3 (exploratory Detector), P4 (Firecracker sandbox), P5 (multi-tenant). See `tasks.md`. |

---

## One-liner pitch

> _"It's a multi-agent pen-tester for code where the **database** — not the
> model and not the prompt — enforces that every claim is backed by quoted
> source the system can re-resolve. Findings without evidence cannot be
> written. Exploits without an independent runner cannot be recorded. That's
> the whole architectural bet."_
