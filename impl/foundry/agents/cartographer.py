"""Cartographer — pipeline of focused passes (FR-030–FR-036a)."""
from __future__ import annotations

from typing import Any

import structlog

from foundry.harness import AgentBase, AgentContext
from foundry.llm import LLMMessage
from foundry.substrate import SubstrateConn

log = structlog.get_logger(__name__)

DOC_KINDS = ["overview", "attack_surface", "trust_boundaries", "data_flows", "threat_model"]


class CartographerAgent(AgentBase):
    role = "cartographer"
    task_kinds = ["cartograph_doc"]

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        kind = task["task_payload"]["doc_kind"]
        symbols = await conn.list_symbols(ctx.evaluation_id)
        # Build a compact digest of the index for the LLM context.
        digest = "\n".join(f"{s['path']}::{s['symbol']}" for s in symbols[:200])

        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"[ROLE=cartographer] [DOC={kind}] "
                    "You are the Cartographer for the Foundry Sec evaluation pipeline. "
                    "Produce a concise security-context document for the requested doc kind. "
                    "Cite real symbols only — they are listed below."
                ),
            ),
            LLMMessage(
                role="user",
                content=f"Index digest:\n{digest}\n\nProduce the {kind} document.",
            ),
        ]
        try:
            resp = await ctx.llm.complete(messages, tier="strong")
            content = resp.text.strip()
        except Exception as e:  # noqa: BLE001
            log.warning("cartographer_pass_failed", kind=kind, error=str(e))
            content = ""

        is_fallback = False
        if not content:
            content = self._fallback(kind, symbols)
            is_fallback = True

        await conn.upsert_security_doc(ctx.evaluation_id, kind, content, is_fallback)
        await conn.log_session(
            ctx.evaluation_id,
            ctx.agent_id,
            self.role,
            "doc_written",
            {"doc_kind": kind, "is_fallback": is_fallback, "length": len(content)},
        )

    @staticmethod
    def _fallback(kind: str, symbols: list[dict[str, Any]]) -> str:
        """FR-036a fallback — empty maps are a Cartographer failure, not graceful degradation."""
        n = len(symbols)
        first = "\n".join(f"- {s['path']}::{s['symbol']}" for s in symbols[:20])
        return (
            f"# {kind.replace('_', ' ').title()} (mechanical fallback)\n\n"
            f"Auto-derived from index ({n} symbols). LLM authoring failed for this pass.\n\n"
            f"## Inventory excerpt\n\n{first}\n"
        )
