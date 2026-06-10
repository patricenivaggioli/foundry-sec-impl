"""CLI: `foundry run --config configs/demo.yaml`."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
import structlog

from foundry.agents import (
    CartographerAgent,
    CoverageGuideAgent,
    DetectorAgent,
    IndexerAgent,
    ReporterAgent,
    TriagerAgent,
    ValidatorAgent,
)
from foundry.config import EvaluationConfig
from foundry.llm import get_client
from foundry.orchestrator import LifecycleOrchestrator
from foundry.substrate import Substrate

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger("foundry.cli")


@click.group()
def cli() -> None:
    """Foundry Sec — multi-agent security evaluation runner."""


@cli.command()
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
@click.option("--output", "output_dir", default="output", type=click.Path())
def run(config_path: str, output_dir: str) -> None:
    """Run a full evaluation against the configured target."""
    cfg = EvaluationConfig.load(config_path)
    asyncio.run(_run(cfg, output_dir))


async def _run(cfg: EvaluationConfig, output_dir: str) -> None:
    substrate = Substrate(cfg.substrate.dsn)
    await substrate.init()
    try:
        async with substrate.conn() as c:
            evaluation_id = await c.create_evaluation(
                cfg.name, cfg.target.path, cfg.target.revision, cfg.model_dump(mode="json")
            )
        log.info("evaluation_created", id=str(evaluation_id))

        llm = get_client(
            strong_model=cfg.llm.strong_model,
            bulk_model=cfg.llm.bulk_model,
            region=cfg.llm.region,
        )

        # Spawn agent workers (each as an asyncio task running its loop graph).
        agent_tasks: list[asyncio.Task] = []

        async def spawn(cls, count: int = 1) -> None:
            for i in range(count):
                ag = await cls.spawn(
                    substrate, llm, evaluation_id, i, cfg.target.path,
                    extras={"testbed": "docker-mock"},
                )
                agent_tasks.append(asyncio.create_task(ag.run(), name=f"{cls.role}-{i}"))

        # ── Phase 0: Index ───────────────────────────────────────────────
        await spawn(IndexerAgent, 1)
        orch = LifecycleOrchestrator(substrate, evaluation_id, cfg.model_dump(mode="json"))
        await orch.kick_index()
        await orch.wait_for_index(timeout_s=120)

        # ── Phase 1: Cartograph + Detect (in parallel) ───────────────────
        await spawn(CartographerAgent, 1)
        await spawn(DetectorAgent, cfg.concurrency.detector)
        await spawn(TriagerAgent, cfg.concurrency.triager)
        await spawn(ValidatorAgent, 1)
        await spawn(CoverageGuideAgent, 1)
        await spawn(ReporterAgent, 1)

        await orch.kick_cartograph()
        await orch.kick_detect()

        # Wait for triage to drain, then validate survivors.
        await orch.wait_for_drain(timeout_s=cfg.budget.wallclock_seconds)
        await orch.kick_validate_survivors()
        await orch.kick_coverage_tick()
        await orch.wait_for_drain(timeout_s=cfg.budget.wallclock_seconds)

        # Final report.
        await orch.kick_report(output_dir)
        await orch.wait_for_drain(timeout_s=120)

        # Cancel agent loops.
        for t in agent_tasks:
            t.cancel()
        await asyncio.gather(*agent_tasks, return_exceptions=True)

        log.info("evaluation_complete", id=str(evaluation_id), output=output_dir)
        click.echo(f"\n✅ Evaluation {evaluation_id} complete. See {output_dir}/.")
    finally:
        await substrate.close()


@cli.command("init-db")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
def init_db(config_path: str) -> None:
    """Apply the substrate migration to the configured DSN."""
    cfg = EvaluationConfig.load(config_path)
    sql = (Path(__file__).parent.parent / "migrations" / "0001_substrate.sql").read_text()
    asyncio.run(_init_db(cfg.substrate.dsn, sql))


async def _init_db(dsn: str, sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    click.echo("✅ Substrate schema applied.")


@cli.command("ui")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8080, type=int)
def ui(config_path: str, host: str, port: int) -> None:
    """Launch the read-only inspector web UI on http://HOST:PORT/."""
    import uvicorn

    from foundry.web import create_app

    cfg = EvaluationConfig.load(config_path)
    app = create_app(cfg.substrate.dsn, config_path=config_path)
    click.echo(f"🔭 Foundry Sec inspector → http://{host}:{port}/")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    cli()
