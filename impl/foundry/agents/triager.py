"""Triager — emits verdict with citations; relies on DB-side citation gate (Principle I)."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import structlog

from foundry.harness import AgentBase, AgentContext
from foundry.llm import LLMMessage
from foundry.substrate import SubstrateConn

log = structlog.get_logger(__name__)


class TriagerAgent(AgentBase):
    role = "triager"
    task_kinds = ["triage"]

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        finding_id = uuid.UUID(task["task_payload"]["finding_id"])
        finding = await conn.get_finding(finding_id)
        if finding is None:
            return

        sym = await conn.get_symbol(
            ctx.evaluation_id, finding["path"], finding["symbol"]
        )
        if sym is None:
            await conn.set_verdict(finding_id, "needs-context", "Symbol vanished from index.")
            return

        callers = await conn.callers_of(ctx.evaluation_id, finding["symbol"])
        sec_map = await conn.get_security_map(ctx.evaluation_id)
        boundaries = sec_map.get("trust_boundaries", "")[:1500]

        messages = [
            LLMMessage(
                role="system",
                content=(
                    "[ROLE=triager] You investigate a candidate finding and assign a verdict. "
                    "Verdict must be one of: true-positive, false-positive, needs-context, duplicate. "
                    "If true-positive, include >=1 citation: an EXACT substring of the function body "
                    "that demonstrates the vulnerability. The substrate REJECTS citations whose "
                    "excerpts are not actual substrings of the indexed body. "
                    "Reply with strict JSON: "
                    '{"verdict": str, "notes": str, "citations": [{"path": str, "symbol": str, "excerpt": str}], "severity": str|null}'
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"[PATH={finding['path']}]\n[SYMBOL={finding['symbol']}]\n"
                    f"Vuln class: {finding['vuln_class']}\n"
                    f"Detector rule: {finding['rule_id']}\n"
                    f"Detector rationale: {finding['detector_rationale']}\n"
                    f"Callers: {[c['caller_symbol'] for c in callers] or 'none'}\n"
                    f"Trust boundaries:\n{boundaries}\n\n"
                    f"[BODY]{sym['body']}[/BODY]"
                ),
            ),
        ]

        resp = await ctx.llm.complete(messages, tier="strong", json_mode=True)
        await conn.log_session(
            ctx.evaluation_id, ctx.agent_id, self.role, "llm_call",
            {"finding_id": str(finding_id)},
            finding_id=finding_id, tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
        )

        try:
            data = json.loads(_extract_json(resp.text))
        except (json.JSONDecodeError, ValueError):
            log.warning("triager_bad_json", text=resp.text[:200])
            await conn.set_verdict(finding_id, "needs-context", "Triager produced unparseable output.")
            return

        verdict = data.get("verdict", "needs-context")
        notes = data.get("notes", "")
        severity = data.get("severity")
        citations = data.get("citations") or []

        # Insert citations FIRST — DB rejects fabrications (Principle I).
        accepted = 0
        for c in citations:
            cid = await conn.add_citation(
                finding_id=finding_id,
                evaluation_id=ctx.evaluation_id,
                cite_path=c.get("path", finding["path"]),
                cite_symbol=c.get("symbol", finding["symbol"]),
                quoted_excerpt=c.get("excerpt", ""),
            )
            if cid is not None:
                accepted += 1

        # Demote true-positive to needs-context if no citation survived the gate.
        if verdict == "true-positive" and accepted == 0:
            log.warning(
                "verdict_demoted",
                finding_id=str(finding_id),
                reason="no citation survived the gate",
            )
            verdict = "needs-context"
            notes = (notes + "\n\n[GATE] No citation resolved against the index.").strip()
            severity = None

        await conn.set_verdict(finding_id, verdict, notes, severity)


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text
