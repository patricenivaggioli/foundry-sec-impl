"""Smoke test for the citation gate (Principle I, enforced at DB layer)."""
import os
import uuid

import pytest

from foundry.substrate import Substrate

DSN = os.environ.get("FOUNDRY_DSN", "postgresql://foundry:foundry@localhost:5432/foundry")


@pytest.mark.asyncio
async def test_citation_gate_rejects_fabrication():
    sub = Substrate(DSN)
    await sub.init()
    try:
        async with sub.conn() as c:
            eid = await c.create_evaluation(
                name="test-cite-gate",
                target_path="/tmp",
                target_revision="r1",
                config={},
            )
            await c.upsert_symbol(
                eid, "a.py", "module.foo", "function", 1, 5,
                body="def foo(x):\n    return x + 1\n",
            )
            agent_id = await c.register_agent(eid, "triager", 0, 1234)
            fid = await c.upsert_candidate(
                eid, "r1", "a.py", "module.foo", "CWE-89", "rule", "R1", "rationale",
            )
            # Real substring → accepted.
            ok = await c.add_citation(
                finding_id=fid, evaluation_id=eid,
                cite_path="a.py", cite_symbol="module.foo",
                quoted_excerpt="return x + 1",
            )
            # Fabricated → rejected (DB trigger).
            bad = await c.add_citation(
                finding_id=fid, evaluation_id=eid,
                cite_path="a.py", cite_symbol="module.foo",
                quoted_excerpt="DROP TABLE users",
            )
            assert ok is not None, "real excerpt should resolve"
            assert bad is None, "fabricated excerpt MUST be rejected by the citation gate"
    finally:
        await sub.close()
