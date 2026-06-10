"""Reporter agent — wraps the SARIF/Markdown writer (Principle II)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from foundry.harness import AgentBase, AgentContext
from foundry.reporter import write_markdown, write_sarif
from foundry.substrate import SubstrateConn

log = structlog.get_logger(__name__)


class ReporterAgent(AgentBase):
    role = "reporter"
    task_kinds = ["report"]

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        out_dir = Path(task["task_payload"].get("output_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)

        # Principle II: only surviving findings reach output.
        findings = await conn.list_findings(
            ctx.evaluation_id, state=None, survived_only=True
        )
        # Attach citations.
        full = []
        for f in findings:
            f["_citations"] = await conn.list_citations(f["id"])
            full.append(f)

        sarif_path = out_dir / "findings.sarif"
        md_path = out_dir / "report.md"
        write_sarif(full, sarif_path)
        write_markdown(full, md_path)

        # Mark findings as reported.
        for f in full:
            await conn.raw.execute(
                "UPDATE findings SET state='reported' WHERE id = $1", f["id"]
            )

        log.info("report_written", count=len(full), sarif=str(sarif_path), md=str(md_path))
