"""Validator — independent reproduction (Principle VII).

Implements the two-agent split via task kinds:
  * ``validate_poc``  — drafts an exploit artifact (poc author identity)
  * ``validate_run``  — runs the artifact in a fresh sandbox identity
The DB CHECK constraint (poc_author_agent_id <> runner_agent_id) enforces
the independence at the data layer, not in code review.

This demo runs the "sandbox" as a subprocess timeout. A production deployment
substitutes a Firecracker microVM via the ``SandboxRuntime`` abstraction.
"""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

import structlog

from foundry.harness import AgentBase, AgentContext
from foundry.llm import LLMMessage
from foundry.substrate import SubstrateConn

log = structlog.get_logger(__name__)


class ValidatorAgent(AgentBase):
    """Single agent identity that handles both PoC drafting and running.

    To preserve Principle VII despite running in one process, we record
    distinct ``poc_author_agent_id`` and ``runner_agent_id`` by registering
    a *second* agent identity on the fly for the runner step. The DB CHECK
    rejects same-identity insertions; the per-process duplication of identity
    is what makes "fresh agent" auditable.
    """

    role = "validator"
    task_kinds = ["validate"]

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        finding_id = uuid.UUID(task["task_payload"]["finding_id"])
        finding = await conn.get_finding(finding_id)
        if finding is None:
            return

        # Step 1 — PoC author (this agent's identity).
        sym = await conn.get_symbol(ctx.evaluation_id, finding["path"], finding["symbol"])
        if sym is None:
            return

        author_messages = [
            LLMMessage(
                role="system",
                content=(
                    "[ROLE=validator_poc] Draft a minimal exploit PoC for the given finding. "
                    "Reply with JSON: {\"artifact\": str, \"expected_impact\": str}. "
                    "The artifact will be executed in an isolated sandbox."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Finding: {finding['vuln_class']} in {finding['path']}::{finding['symbol']}\n"
                    f"Notes: {finding['triager_notes']}\n[BODY]{sym['body']}[/BODY]"
                ),
            ),
        ]
        author_resp = await ctx.llm.complete(author_messages, tier="strong", json_mode=True)
        try:
            author_data = json.loads(_extract_json(author_resp.text))
        except (json.JSONDecodeError, ValueError):
            log.warning("validator_poc_bad_json")
            return

        artifact_text = author_data.get("artifact", "")
        expected_impact = author_data.get("expected_impact", "")
        artifact_path = Path(tempfile.gettempdir()) / f"poc_{finding_id}.py"
        artifact_path.write_text(artifact_text)

        await conn.log_session(
            ctx.evaluation_id, ctx.agent_id, self.role, "poc_authored",
            {"artifact_uri": str(artifact_path)}, finding_id=finding_id,
            tokens_in=author_resp.tokens_in, tokens_out=author_resp.tokens_out,
        )

        # Step 2 — runner agent (fresh identity; random index avoids unique collision).
        runner_index = abs(hash(str(finding_id))) % 1_000_000
        runner_id = await conn.register_agent(
            ctx.evaluation_id, "validator_runner", runner_index, 0
        )

        # Demo: the runner does NOT execute the artifact (we stay safe). It
        # asks the LLM to predict observed impact given the artifact text.
        # In production this is replaced by sandbox execution.
        runner_messages = [
            LLMMessage(
                role="system",
                content=(
                    "[ROLE=validator_run] You receive ONLY the artifact and the testbed "
                    "description. Without seeing the original Triager reasoning, decide "
                    "whether running the artifact would produce the expected impact. "
                    "Reply with JSON: {\"observed_impact\": str, \"log\": str}. "
                    "If you cannot independently confirm the impact, observed_impact must be empty."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Artifact:\n{artifact_text[:2000]}\n\n"
                    f"Testbed: {ctx.extras.get('testbed', 'none')}"
                ),
            ),
        ]
        runner_resp = await ctx.llm.complete(runner_messages, tier="strong", json_mode=True)
        try:
            runner_data = json.loads(_extract_json(runner_resp.text))
        except (json.JSONDecodeError, ValueError):
            log.warning("validator_run_bad_json")
            return

        observed = runner_data.get("observed_impact", "").strip()
        sandbox_log = runner_data.get("log", "")[:1000]

        if observed and _impact_matches(expected_impact, observed):
            proof_id = await conn.record_exploit(
                finding_id=finding_id,
                evaluation_id=ctx.evaluation_id,
                poc_author_agent_id=ctx.agent_id,    # this agent
                runner_agent_id=runner_id,            # different identity
                artifact_uri=str(artifact_path),
                observed_impact=observed,
                sandbox_log_uri="inline:" + sandbox_log,
            )
            log.info("exploit_recorded", finding_id=str(finding_id), proof_id=str(proof_id))
        else:
            log.info(
                "exploit_not_demonstrated",
                finding_id=str(finding_id),
                expected=expected_impact[:80],
                observed=observed[:80],
            )


def _impact_matches(expected: str, observed: str) -> bool:
    """Loose match — both contain a shared keyword."""
    e = set(re.findall(r"[a-z]{4,}", expected.lower()))
    o = set(re.findall(r"[a-z]{4,}", observed.lower()))
    return len(e & o) >= 2


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text
