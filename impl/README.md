# Foundry Sec — Reference Implementation (Demo)

A runnable demo of the Foundry Security Spec architecture.

> ⚠️ This is a **demonstration** of the architecture in `../spec.md`, `../plan.md`, and `../tasks.md`.
> It is **not** production-ready. It implements P0+P1+P2 of the plan with stubs for P3+.

## What this implements

- **Substrate:** Postgres 16 with atomic claim (`SKIP LOCKED`), heartbeat-driven liveness, insert-time citation resolver (Principle I enforced at the DB layer), stable fingerprints excluding line numbers (Principle VIII), atomic persist (Principle XI).
- **Eight roles** as LangGraph state machines:
  - **Orchestrator** — two lanes: lifecycle (asyncio, no LLM) and conversational (LangGraph, LLM-backed).
  - **Indexer** — tree-sitter Python frontend; produces queryable index; gates fleet spawn (FR-003/FR-024).
  - **Cartographer** — pipeline of focused passes per document type, each persisted atomically.
  - **Detector** — Semgrep rule-sweep mode + LLM-evaluated function checks.
  - **Triager** — investigates each candidate, emits verdict with citations; **DB layer rejects fabricated citations**.
  - **Validator** — independent runner (different agent identity) reproduces exploits in a sandbox.
  - **Coverage-Guide** — multi-dimensional coverage state (entry points × CWE classes × trust boundaries × goals).
  - **Reporter** — SARIF 2.1.0 + Markdown rollup; only surviving findings reach output (Principle II).
- **LLM provider:** Mistral.ai with two tiers (Large/Small or Codestral), pluggable to a mock client when `MISTRAL_API_KEY` is unset (Principle V — adaptive backoff on 429s).
- **Sandbox:** Docker container per agent with iptables egress allowlist (Principle IX).

## Quick start

```bash
# 1. Bring up Postgres
docker compose -f deploy/compose.yml up -d

# 2. Install
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# 3. Apply schema
export FOUNDRY_DSN=postgresql://foundry:foundry@localhost:5432/foundry
foundry init-db --config configs/demo.yaml

# 4. (Optional) export your Mistral key — without it, the mock LLM is used
export MISTRAL_API_KEY=...

# 5. Run an evaluation against the fixture target
foundry run --config configs/demo.yaml --output output

# 6. Read the report
cat output/report.md
cat output/findings.sarif
```

## Layout

```
impl/
├── foundry/
│   ├── substrate/        # DB access, work queue, finding store, citation resolver
│   ├── harness/          # LangGraph agent base classes + tool registry
│   ├── llm/              # Mistral client + mock + adaptive backoff
│   ├── agents/           # The 8 roles, each as a LangGraph state machine
│   ├── orchestrator/     # Lifecycle lane + conversational lane
│   ├── reporter/         # SARIF + Markdown emitters
│   └── cli.py            # Entry point
├── migrations/           # SQL schema + RLS policies + insert-time triggers
├── deploy/               # docker-compose for Postgres
├── fixtures/             # Vulnerable target + sample configs
├── configs/              # Sample evaluation configs (YAML)
└── tests/                # Unit + chaos tests
```

## What it doesn't yet do

- Phase P3 (exploratory Detector, full Coverage-Guide multi-dim transitions): partially stubbed.
- Phase P4 (Firecracker microVM Validator): demo uses Docker.
- Phase P5 (multi-tenancy, k8s): single-tenant, single-machine only.

See `../tasks.md` for the full backlog.

## Constitution check

Run before sending any PR:

```bash
make analyze    # checks plan.md + tasks.md against ../constitution.md
```
