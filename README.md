# Foundry Sec — Reference Implementation

[![Status](https://img.shields.io/badge/Status-v0.1.0-blue.svg)](CHANGELOG.md)
[![License](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)

A Python implementation of the [Foundry Security Spec](spec.md) — a multi-agent AI security evaluation pipeline. This repo contains both the original spec (from Cisco) and a working implementation in [`impl/`](impl/).

![Pipeline dashboard showing 19 findings across 8 agent roles](docs/images/inspector-dashboard.png)

![Agent workflow graph showing orchestrator → indexer → cartographer → detector → triager → validator → reporter](docs/images/inspector-findings.png)

## Architecture

The pipeline chains eight agents to evaluate a target codebase for security vulnerabilities:

```
INDEXER → CARTOGRAPHER → DETECTOR → TRIAGER → VALIDATOR → REPORTER
                                                         ↑
                                             COVERAGE GUIDE (oversight)
```

All agents share a PostgreSQL substrate for coordination, findings, and deduplication.

## Prerequisites

- Python 3.11+
- Docker (for PostgreSQL via Compose)
- A [Mistral AI](https://console.mistral.ai/) API key — or run without one to use the built-in mock client

## Installation

```bash
cd impl
pip install -e ".[dev]"
```

## Configuration

Evaluations are driven by a YAML config file. A demo config is provided at [`impl/configs/demo.yaml`](impl/configs/demo.yaml):

```yaml
name: demo

substrate:
  dsn: ${env:FOUNDRY_DSN}      # PostgreSQL connection string (from env)

llm:
  provider: mistral
  strong_model: mistral-large-latest
  bulk_model: mistral-small-latest
  region: eu                   # "eu" or "us"

target:
  path: ./fixtures/vulnerable_app
  revision: demo-r1

budget:
  tokens: 200000
  wallclock_seconds: 600

concurrency:
  detector: 2
  triager: 2

goals:
  attack_goals:
    - data_exfiltration
    - rce
    - auth_bypass
```

Config values can reference environment variables with `${env:VAR_NAME}`.

## Usage

### 1. Start PostgreSQL

```bash
cd impl
docker compose -f deploy/compose.yml up -d
```

### 2. Set environment variables

```bash
export FOUNDRY_DSN="postgresql://foundry:foundry@localhost:5432/foundry"
export MISTRAL_API_KEY="your-api-key"   # optional — omit to use the mock client
```

### 3. Initialise the database schema

```bash
foundry init-db --config configs/demo.yaml
```

### 4. Run an evaluation

```bash
foundry run --config configs/demo.yaml --output output/
```

Output files are written to the `output/` directory:
- `output/report.md` — human-readable findings report
- `output/findings.sarif` — machine-readable SARIF file

### 5. Inspect results (optional web UI)

```bash
foundry ui --config configs/demo.yaml --host 127.0.0.1 --port 8080
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080).

## Without a Mistral API key

If `MISTRAL_API_KEY` is not set, the app falls back to a deterministic **mock client** that produces structurally valid responses. This is useful for testing the pipeline wiring end-to-end without hitting the API.

## Running tests

```bash
cd impl
pytest
```

## Project structure

```
impl/
├── configs/          # Example evaluation configs
├── deploy/           # Docker Compose for PostgreSQL
├── fixtures/         # Sample vulnerable app for demo
├── foundry/
│   ├── agents/       # Eight agent implementations
│   ├── harness/      # Agent base class
│   ├── llm/          # Mistral client + mock
│   ├── orchestrator/ # Lifecycle coordination
│   ├── reporter/     # SARIF + markdown output
│   ├── substrate/    # PostgreSQL interface
│   ├── web/          # Read-only inspector UI (FastAPI)
│   ├── cli.py        # CLI entry point
│   └── config.py     # Pydantic config models
├── migrations/       # SQL schema
├── output/           # Evaluation outputs (git-ignored)
└── tests/
```

## Spec reference

The original Foundry specification (from Cisco) remains in this repo:
- [`spec.md`](spec.md) — full specification with agent roles and requirements
- [`constitution.md`](constitution.md) — eleven inviolable principles
- [`GLOSSARY.md`](GLOSSARY.md) — terminology reference

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

Original spec content © 2026 Cisco Systems, Inc.  
Implementation (`impl/`) © 2026 Patrice Nivaggioli  
Both licensed under [CC BY 4.0](LICENSE).
