"""Indexer — tree-sitter Python frontend (FR-020/FR-021/FR-022/FR-024).

Deterministic parser is the SOLE source for the function inventory and call
graph. LLM enrichment is intentionally absent here — the spec authors lost
this exact bet on first build (see spec §5.2 FR-020 rationale).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from foundry.harness import AgentBase, AgentContext
from foundry.substrate import SubstrateConn

log = structlog.get_logger(__name__)

PY_LANGUAGE = Language(tspython.language())


class IndexerAgent(AgentBase):
    role = "indexer"
    task_kinds = ["index"]

    async def handle_task(
        self, ctx: AgentContext, task: dict[str, Any], conn: SubstrateConn
    ) -> None:
        payload = task["task_payload"]
        action = payload.get("action", "build")
        if action == "build":
            await self._build_index(ctx, conn)
            await conn.signal_index_ready(ctx.evaluation_id)

    async def _build_index(self, ctx: AgentContext, conn: SubstrateConn) -> None:
        root = Path(ctx.target_root).resolve()
        parser = Parser(PY_LANGUAGE)
        n_files = 0
        n_symbols = 0
        for py_file in root.rglob("*.py"):
            if "test_" in py_file.name or ".venv" in str(py_file):
                continue
            rel = str(py_file.relative_to(root))
            text = py_file.read_text()
            tree = parser.parse(text.encode())
            module_fqn = rel.replace(os.sep, ".").removesuffix(".py")
            symbols = _extract_symbols(tree.root_node, text, module_fqn)
            for sym in symbols:
                await conn.upsert_symbol(
                    ctx.evaluation_id,
                    rel,
                    sym["fqn"],
                    sym["kind"],
                    sym["start_line"],
                    sym["end_line"],
                    sym["body"],
                )
                for callee in sym["callees"]:
                    await conn.add_call_edge(ctx.evaluation_id, rel, sym["fqn"], callee)
                n_symbols += 1
            n_files += 1
        log.info("index_built", files=n_files, symbols=n_symbols)


def _extract_symbols(root: Node, source: str, module_fqn: str) -> list[dict[str, Any]]:
    """Walk the AST collecting function/method definitions and their call edges."""
    out: list[dict[str, Any]] = []
    src_bytes = source.encode()

    def walk(node: Node, class_stack: list[str]) -> None:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                cls_name = src_bytes[name_node.start_byte : name_node.end_byte].decode()
                for child in node.children:
                    walk(child, class_stack + [cls_name])
                return
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = src_bytes[name_node.start_byte : name_node.end_byte].decode()
            qualified = ".".join([module_fqn] + class_stack + [name])
            kind = "method" if class_stack else "function"
            body_text = src_bytes[node.start_byte : node.end_byte].decode()
            callees = _extract_calls(node, src_bytes)
            out.append(
                {
                    "fqn": qualified,
                    "kind": kind,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": body_text,
                    "callees": callees,
                }
            )
            return
        for child in node.children:
            walk(child, class_stack)

    walk(root, [])
    return out


def _extract_calls(fn_node: Node, src_bytes: bytes) -> list[str]:
    callees: set[str] = set()

    def walk(n: Node) -> None:
        if n.type == "call":
            fn = n.child_by_field_name("function")
            if fn is not None:
                txt = src_bytes[fn.start_byte : fn.end_byte].decode().strip()
                txt = txt.split("(")[0].strip()
                if txt:
                    callees.add(txt)
        for ch in n.children:
            walk(ch)

    walk(fn_node)
    return sorted(callees)
