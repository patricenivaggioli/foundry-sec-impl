# Foundry Sec — Implementation

The runnable demo lives under [`impl/`](./impl/). The architecture, principles,
and task backlog live at the repo root:

- [`constitution.md`](./constitution.md) — 11 inviolable principles
- [`spec.md`](./spec.md) — system specification
- [`plan.md`](./plan.md) — implementation plan resolving every clarification
- [`tasks.md`](./tasks.md) — 51-task backlog across phases P0–P5
- [`impl/`](./impl/) — Python / Postgres / LangGraph reference implementation
  (P0+P1+P2 scope, Mistral.ai LLM with mock fallback)

## Try the demo

```bash
cd impl
docker compose -f deploy/compose.yml up -d
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export FOUNDRY_DSN=postgresql://foundry:foundry@localhost:5432/foundry
foundry init-db --config configs/demo.yaml
foundry run --config configs/demo.yaml --output output
cat output/report.md
```

Without `MISTRAL_API_KEY`, the demo falls back to a deterministic mock LLM that
produces citation-resolvable outputs so the pipeline runs end-to-end offline.
With a real key, every LLM call goes to Mistral Large / Small.
