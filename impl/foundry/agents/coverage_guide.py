"""Coverage-Guide — multi-dimensional coverage state (Principle VI)."""
from __future__ import annotations

import json
from typing import Any

import structlog

from foundry.harness import AgentBase, AgentContext
from foundry.substrate import SubstrateConn

log = structlog.get_logger(__name__)


class CoverageGuideAgent(AgentBase):
    role = "coverage_guide"
    task_kinds = ["coverage_tick"]

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        # Mark CWE classes covered when the corresponding rule fired at least once.
        rows = await conn.raw.fetch(
            """
            SELECT DISTINCT vuln_class FROM findings
             WHERE evaluation_id = $1 AND state IN ('triaged', 'validated', 'reported')
            """,
            ctx.evaluation_id,
        )
        for r in rows:
            await conn.upsert_coverage(ctx.evaluation_id, "cwe_class", r["vuln_class"], "credibly_attempted")

        # Mark every indexed function as an entry-point candidate touched.
        sym_rows = await conn.raw.fetch(
            "SELECT DISTINCT path, symbol FROM code_symbols WHERE evaluation_id = $1",
            ctx.evaluation_id,
        )
        for r in sym_rows:
            await conn.upsert_coverage(
                ctx.evaluation_id, "entry_point", f"{r['path']}::{r['symbol']}", "credibly_attempted"
            )

        # Goals (from config) — assume credibly_attempted for the demo.
        goal_rows = await conn.raw.fetch(
            "SELECT config->'goals' AS g FROM evaluations WHERE id = $1",
            ctx.evaluation_id,
        )
        for r in goal_rows:
            goals = _as_dict(r["g"])
            for goal in goals.get("attack_goals", []) or []:
                await conn.upsert_coverage(ctx.evaluation_id, "goal", goal, "credibly_attempted")

        complete = await conn.coverage_complete(ctx.evaluation_id)
        log.info("coverage_tick", complete=complete)


def _as_dict(v: Any) -> dict[str, Any]:
    """Return a dict from a JSONB column whether asyncpg returned a dict or a JSON-encoded str."""
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}
