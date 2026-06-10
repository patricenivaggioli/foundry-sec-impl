"""Detector — rule-sweep mode (FR-037).

Each task is a (function, rule) pair: the LLM-evaluated check asks whether
the function exhibits the rule's vulnerability class. Function-granularity
with caller/callee context is the unit at which an LLM can reason about data
flow without exhausting context (see FR-037 rationale in spec.md).
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from foundry.harness import AgentBase, AgentContext
from foundry.llm import LLMMessage
from foundry.substrate import SubstrateConn

log = structlog.get_logger(__name__)


# A tiny built-in rule corpus for the demo. Real deployments load from
# a configured corpus (FR-041).
RULES = [
    {
        "id": "FOUNDRY-SQLI-001",
        "cwe": "CWE-89",
        "name": "SQL injection via string concatenation",
        "description": "Function constructs SQL by concatenating untrusted input.",
    },
    {
        "id": "FOUNDRY-CMDI-001",
        "cwe": "CWE-78",
        "name": "OS command injection",
        "description": "Function passes untrusted input to a shell command.",
    },
    {
        "id": "FOUNDRY-DESER-001",
        "cwe": "CWE-502",
        "name": "Insecure deserialization",
        "description": "Function deserializes untrusted data with pickle/yaml.",
    },
    {
        "id": "FOUNDRY-CODE-001",
        "cwe": "CWE-94",
        "name": "Code injection via eval/exec",
        "description": "Function evaluates a string as code.",
    },
]


class DetectorAgent(AgentBase):
    role = "detector"
    task_kinds = ["detect_rule"]

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        payload = task["task_payload"]
        path = payload["path"]
        symbol = payload["symbol"]
        rule_id = payload["rule_id"]
        rule = next((r for r in RULES if r["id"] == rule_id), None)
        if rule is None:
            return

        sym = await conn.get_symbol(ctx.evaluation_id, path, symbol)
        if sym is None:
            return

        sec_map = await conn.get_security_map(ctx.evaluation_id)
        boundaries = sec_map.get("trust_boundaries", "")[:1500]

        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"[ROLE=detector] [RULE={rule_id}] "
                    "You evaluate a single function against a single rule. "
                    "Reply with strict JSON: {\"is_vuln\": bool, \"rule_id\": str, \"reason\": str}."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Rule: {rule['name']}\n"
                    f"Description: {rule['description']}\n"
                    f"Trust boundaries digest:\n{boundaries}\n\n"
                    f"Function: {symbol}\n"
                    f"[BODY]{sym['body']}[/BODY]"
                ),
            ),
        ]

        resp = await ctx.llm.complete(messages, tier="bulk", json_mode=True)
        await conn.log_session(
            ctx.evaluation_id,
            ctx.agent_id,
            self.role,
            "llm_call",
            {"rule_id": rule_id, "symbol": symbol},
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
        )

        try:
            data = json.loads(_extract_json(resp.text))
        except (json.JSONDecodeError, ValueError):
            log.warning("detector_bad_json", text=resp.text[:200])
            return

        if data.get("is_vuln"):
            target_revision = await self._target_revision(ctx, conn)
            finding_id = await conn.upsert_candidate(
                ctx.evaluation_id,
                target_revision=target_revision,
                path=path,
                symbol=symbol,
                vuln_class=rule["cwe"],
                detector_mode="rule",
                rule_id=rule_id,
                rationale=data.get("reason", ""),
            )
            # Queue triage.
            await conn.enqueue(
                ctx.evaluation_id,
                "triage",
                {"finding_id": str(finding_id)},
                priority=50,
            )
            log.info("candidate_emitted", rule=rule_id, symbol=symbol)

    @staticmethod
    async def _target_revision(ctx: AgentContext, conn: SubstrateConn) -> str:
        row = await conn.raw.fetchrow(
            "SELECT target_revision FROM evaluations WHERE id = $1",
            ctx.evaluation_id,
        )
        return row["target_revision"] if row else "unknown"


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text
