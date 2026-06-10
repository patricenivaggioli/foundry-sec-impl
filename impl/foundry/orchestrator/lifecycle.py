"""Lifecycle orchestrator: phase planner + budget watcher."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

from foundry.agents.detector import RULES
from foundry.agents.cartographer import DOC_KINDS
from foundry.substrate import Substrate

log = structlog.get_logger(__name__)


class LifecycleOrchestrator:
    def __init__(self, substrate: Substrate, evaluation_id: uuid.UUID, config: dict[str, Any]):
        self.substrate = substrate
        self.evaluation_id = evaluation_id
        self.config = config

    async def kick_index(self) -> None:
        async with self.substrate.conn() as c:
            await c.enqueue(self.evaluation_id, "index", {"action": "build"}, priority=100)
        log.info("phase_index_queued")

    async def wait_for_index(self, timeout_s: float = 600) -> None:
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            async with self.substrate.conn() as c:
                if await c.index_ready(self.evaluation_id):
                    log.info("index_ready")
                    return
            await asyncio.sleep(1.0)
        raise TimeoutError("Index never became ready")

    async def kick_cartograph(self) -> None:
        async with self.substrate.conn() as c:
            for kind in DOC_KINDS:
                await c.enqueue(
                    self.evaluation_id, "cartograph_doc", {"doc_kind": kind}, priority=80
                )
        log.info("phase_cartograph_queued", count=len(DOC_KINDS))

    async def kick_detect(self) -> None:
        """Plan one (function × rule) task per code symbol."""
        async with self.substrate.conn() as c:
            symbols = await c.list_symbols(self.evaluation_id)
            for sym in symbols:
                for rule in RULES:
                    await c.enqueue(
                        self.evaluation_id,
                        "detect_rule",
                        {
                            "path": sym["path"],
                            "symbol": sym["symbol"],
                            "rule_id": rule["id"],
                        },
                        priority=60,
                    )
        log.info(
            "phase_detect_queued",
            tasks=len(symbols) * len(RULES),
            symbols=len(symbols),
            rules=len(RULES),
        )

    async def kick_coverage_tick(self) -> None:
        async with self.substrate.conn() as c:
            await c.enqueue(self.evaluation_id, "coverage_tick", {}, priority=40)

    async def kick_validate_survivors(self) -> None:
        """Queue validate tasks for every true-positive that survived the gate."""
        async with self.substrate.conn() as c:
            findings = await c.list_findings(
                self.evaluation_id, state="triaged", survived_only=True
            )
            for f in findings:
                await c.enqueue(
                    self.evaluation_id, "validate", {"finding_id": str(f["id"])}, priority=70
                )
        log.info("phase_validate_queued", count=len(findings))

    async def kick_report(self, output_dir: str) -> None:
        async with self.substrate.conn() as c:
            await c.enqueue(
                self.evaluation_id, "report", {"output_dir": output_dir}, priority=30
            )

    async def queue_idle(self) -> bool:
        async with self.substrate.conn() as c:
            row = await c.raw.fetchrow(
                """
                SELECT COUNT(*) FILTER (WHERE state IN ('ready','claimed')) AS pending
                  FROM work_queue WHERE evaluation_id = $1
                """,
                self.evaluation_id,
            )
            return (row["pending"] or 0) == 0

    async def wait_for_drain(self, timeout_s: float = 1800) -> None:
        deadline = asyncio.get_event_loop().time() + timeout_s
        last_pending = -1
        idle_ticks = 0
        while asyncio.get_event_loop().time() < deadline:
            async with self.substrate.conn() as c:
                row = await c.raw.fetchrow(
                    """
                    SELECT COUNT(*) FILTER (WHERE state IN ('ready','claimed')) AS pending,
                           COUNT(*) FILTER (WHERE state='claimed') AS claimed
                      FROM work_queue WHERE evaluation_id = $1
                    """,
                    self.evaluation_id,
                )
            pending = row["pending"] or 0
            if pending == 0:
                idle_ticks += 1
                if idle_ticks >= 3:
                    return
            else:
                idle_ticks = 0
            if pending != last_pending:
                log.info("queue_drain_progress", pending=pending, claimed=row["claimed"])
                last_pending = pending
            await asyncio.sleep(1.0)
        raise TimeoutError("Queue did not drain within timeout")
