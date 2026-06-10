"""Shared agent harness — a LangGraph state machine wrapping the claim/heartbeat/release loop.

Every role inherits from ``AgentBase``. The base provides the LangGraph
"work loop" graph: claim → execute (role-specific node) → heartbeat → loop
until the stop condition fires.

LangGraph here is the *intra-agent* coordinator (matches plan §1.13). Inter-agent
coordination is exclusively through the substrate.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TypedDict

import structlog
from langgraph.graph import END, StateGraph

from foundry.llm import LLMClient
from foundry.substrate import Substrate, SubstrateConn

log = structlog.get_logger(__name__)


@dataclass
class AgentContext:
    role: str
    instance_index: int
    evaluation_id: uuid.UUID
    agent_id: uuid.UUID
    substrate: Substrate
    llm: LLMClient
    target_root: str
    extras: dict[str, Any] = field(default_factory=dict)


class WorkState(TypedDict, total=False):
    task: dict[str, Any] | None
    iteration: int
    stop: bool
    last_error: str | None


HandlerFn = Callable[[AgentContext, dict[str, Any], SubstrateConn], Coroutine[Any, Any, None]]


def build_loop_graph(
    ctx: AgentContext,
    task_kinds: list[str],
    handler: HandlerFn,
    max_idle_iterations: int = 1800,
    idle_sleep_s: float = 1.0,
) -> Any:
    """Build the work-loop graph: claim → handle → heartbeat → loop."""

    idle_count = {"value": 0}

    async def claim_node(state: WorkState) -> WorkState:
        async with ctx.substrate.conn() as c:
            await c.heartbeat(ctx.agent_id)
            task = await c.claim(ctx.evaluation_id, ctx.agent_id, task_kinds)
        if task is None:
            idle_count["value"] += 1
            await asyncio.sleep(idle_sleep_s)
            return {**state, "task": None}
        idle_count["value"] = 0
        log.info(
            "task_claimed",
            role=ctx.role,
            task_id=str(task["id"]),
            kind=task["task_kind"],
        )
        return {**state, "task": task}

    async def handle_node(state: WorkState) -> WorkState:
        task = state.get("task")
        if not task:
            return state
        try:
            async with ctx.substrate.conn() as c:
                await handler(ctx, task, c)
                await c.complete(task["id"])
                await c.log_session(
                    ctx.evaluation_id,
                    ctx.agent_id,
                    ctx.role,
                    "task_done",
                    {"task_kind": task["task_kind"], "task_id": str(task["id"])},
                )
            return {**state, "iteration": state.get("iteration", 0) + 1, "last_error": None}
        except Exception as e:  # noqa: BLE001 - log and requeue
            log.exception("task_failed", role=ctx.role, task_id=str(task["id"]))
            async with ctx.substrate.conn() as c:
                await c.fail(task["id"], str(e))
            return {**state, "last_error": str(e)}

    async def heartbeat_node(state: WorkState) -> WorkState:
        async with ctx.substrate.conn() as c:
            await c.heartbeat(ctx.agent_id)
        return state

    def loop_or_stop(state: WorkState) -> str:
        if state.get("stop"):
            return END
        if idle_count["value"] >= max_idle_iterations:
            return END
        return "claim"

    g = StateGraph(WorkState)
    g.add_node("claim", claim_node)
    g.add_node("handle", handle_node)
    g.add_node("heartbeat", heartbeat_node)
    g.set_entry_point("claim")
    g.add_edge("claim", "handle")
    g.add_edge("handle", "heartbeat")
    g.add_conditional_edges("heartbeat", loop_or_stop, {"claim": "claim", END: END})
    return g.compile()


class AgentBase:
    """Subclass and override ``handle_task``."""

    role: str = "abstract"
    task_kinds: list[str] = []

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        raise NotImplementedError

    async def run(self) -> None:
        graph = build_loop_graph(self.ctx, self.task_kinds, self.handle_task)
        await graph.ainvoke({"iteration": 0, "stop": False})

    @classmethod
    async def spawn(
        cls,
        substrate: Substrate,
        llm: LLMClient,
        evaluation_id: uuid.UUID,
        instance_index: int,
        target_root: str,
        extras: dict[str, Any] | None = None,
    ) -> "AgentBase":
        async with substrate.conn() as c:
            agent_id = await c.register_agent(
                evaluation_id, cls.role, instance_index, os.getpid()
            )
        ctx = AgentContext(
            role=cls.role,
            instance_index=instance_index,
            evaluation_id=evaluation_id,
            agent_id=agent_id,
            substrate=substrate,
            llm=llm,
            target_root=target_root,
            extras=extras or {},
        )
        return cls(ctx)
