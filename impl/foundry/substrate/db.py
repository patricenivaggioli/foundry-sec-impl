"""Substrate — Postgres-backed coordination layer.

Encodes constitutional invariants:
  * Principle I  — citation resolution at INSERT time (DB trigger)
  * Principle III — heartbeat-driven liveness
  * Principle IV — atomic claim via SKIP LOCKED
  * Principle VII — exploit_proofs.runner_agent_id != poc_author_agent_id (CHECK)
  * Principle VIII — fingerprint excludes line numbers/snippets (generated column)
  * Principle XI — atomic persist via UPSERT, no delete-then-write
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class SubstrateConn:
    """Thin wrapper around an asyncpg connection with role-aware helpers."""

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    @property
    def raw(self) -> asyncpg.Connection:
        return self._conn

    # ── Evaluations ────────────────────────────────────────────────────────

    async def create_evaluation(
        self, name: str, target_path: str, target_revision: str, config: dict[str, Any]
    ) -> uuid.UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO evaluations (name, target_path, target_revision, config)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING id
            """,
            name, target_path, target_revision, json.dumps(config),
        )
        return row["id"]

    # ── Agents ─────────────────────────────────────────────────────────────

    async def register_agent(
        self, evaluation_id: uuid.UUID, role: str, instance_index: int, pid: int
    ) -> uuid.UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO agents (evaluation_id, role, instance_index, pid, state)
            VALUES ($1, $2, $3, $4, 'running')
            RETURNING id
            """,
            evaluation_id, role, instance_index, pid,
        )
        return row["id"]

    async def heartbeat(self, agent_id: uuid.UUID) -> None:
        await self._conn.execute("SELECT heartbeat($1)", agent_id)

    async def stale_agents(self, ttl_seconds: int = 90) -> list[uuid.UUID]:
        rows = await self._conn.fetch(
            """
            SELECT id FROM agents
             WHERE state = 'running'
               AND last_heartbeat < now() - make_interval(secs => $1)
            """,
            ttl_seconds,
        )
        return [r["id"] for r in rows]

    # ── Work queue (Principle IV) ──────────────────────────────────────────

    async def enqueue(
        self,
        evaluation_id: uuid.UUID,
        task_kind: str,
        payload: dict[str, Any],
        priority: int = 100,
    ) -> uuid.UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO work_queue (evaluation_id, task_kind, task_payload, priority)
            VALUES ($1, $2, $3::jsonb, $4)
            RETURNING id
            """,
            evaluation_id, task_kind, json.dumps(payload), priority,
        )
        return row["id"]

    async def claim(
        self,
        evaluation_id: uuid.UUID,
        agent_id: uuid.UUID,
        kinds: list[str],
    ) -> dict[str, Any] | None:
        row = await self._conn.fetchrow(
            "SELECT * FROM claim_one($1, $2, $3::text[])",
            evaluation_id, agent_id, kinds,
        )
        if row is None or row["id"] is None:
            return None
        d = dict(row)
        if isinstance(d.get("task_payload"), str):
            d["task_payload"] = json.loads(d["task_payload"])
        return d

    async def complete(self, task_id: uuid.UUID) -> None:
        await self._conn.execute(
            "UPDATE work_queue SET state='done', updated_at=now() WHERE id = $1",
            task_id,
        )

    async def fail(self, task_id: uuid.UUID, error: str) -> None:
        await self._conn.execute(
            """
            UPDATE work_queue
               SET state = CASE WHEN attempts >= 3 THEN 'failed' ELSE 'ready' END,
                   claimed_by = NULL,
                   claim_expires_at = NULL,
                   last_error = $2,
                   updated_at = now()
             WHERE id = $1
            """,
            task_id, error,
        )

    # ── Index store ────────────────────────────────────────────────────────

    async def upsert_symbol(
        self,
        evaluation_id: uuid.UUID,
        path: str,
        symbol: str,
        kind: str,
        start_line: int,
        end_line: int,
        body: str,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO code_symbols (evaluation_id, path, symbol, kind, start_line, end_line, body)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (evaluation_id, path, symbol) DO UPDATE SET
                kind = EXCLUDED.kind,
                start_line = EXCLUDED.start_line,
                end_line = EXCLUDED.end_line,
                body = EXCLUDED.body
            """,
            evaluation_id, path, symbol, kind, start_line, end_line, body,
        )

    async def add_call_edge(
        self, evaluation_id: uuid.UUID, caller_path: str, caller_symbol: str, callee_symbol: str
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO call_edges (evaluation_id, caller_path, caller_symbol, callee_symbol)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING
            """,
            evaluation_id, caller_path, caller_symbol, callee_symbol,
        )

    async def list_symbols(self, evaluation_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = await self._conn.fetch(
            "SELECT path, symbol, kind, start_line, end_line, body FROM code_symbols WHERE evaluation_id = $1",
            evaluation_id,
        )
        return [dict(r) for r in rows]

    async def get_symbol(
        self, evaluation_id: uuid.UUID, path: str, symbol: str
    ) -> dict[str, Any] | None:
        row = await self._conn.fetchrow(
            "SELECT * FROM code_symbols WHERE evaluation_id = $1 AND path = $2 AND symbol = $3",
            evaluation_id, path, symbol,
        )
        return dict(row) if row else None

    async def callers_of(
        self, evaluation_id: uuid.UUID, symbol: str
    ) -> list[dict[str, Any]]:
        rows = await self._conn.fetch(
            "SELECT caller_path, caller_symbol FROM call_edges WHERE evaluation_id = $1 AND callee_symbol = $2",
            evaluation_id, symbol,
        )
        return [dict(r) for r in rows]

    async def signal_index_ready(self, evaluation_id: uuid.UUID) -> None:
        await self._conn.execute(
            """
            INSERT INTO index_gate (evaluation_id, queryable, released_at)
            VALUES ($1, true, now())
            ON CONFLICT (evaluation_id) DO UPDATE SET
                queryable = true, released_at = now()
            """,
            evaluation_id,
        )

    async def index_ready(self, evaluation_id: uuid.UUID) -> bool:
        row = await self._conn.fetchrow(
            "SELECT queryable FROM index_gate WHERE evaluation_id = $1",
            evaluation_id,
        )
        return bool(row and row["queryable"])

    # ── Security map ────────────────────────────────────────────────────────

    async def upsert_security_doc(
        self, evaluation_id: uuid.UUID, doc_kind: str, content: str, is_fallback: bool = False
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO security_map (evaluation_id, doc_kind, content, is_fallback, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (evaluation_id, doc_kind) DO UPDATE SET
                content = EXCLUDED.content,
                is_fallback = EXCLUDED.is_fallback,
                updated_at = now()
            """,
            evaluation_id, doc_kind, content, is_fallback,
        )

    async def get_security_map(self, evaluation_id: uuid.UUID) -> dict[str, str]:
        rows = await self._conn.fetch(
            "SELECT doc_kind, content FROM security_map WHERE evaluation_id = $1",
            evaluation_id,
        )
        return {r["doc_kind"]: r["content"] for r in rows}

    # ── Findings (Principle VIII fingerprints) ─────────────────────────────

    async def upsert_candidate(
        self,
        evaluation_id: uuid.UUID,
        target_revision: str,
        path: str,
        symbol: str,
        vuln_class: str,
        detector_mode: str,
        rule_id: str | None,
        rationale: str,
    ) -> uuid.UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO findings
                (evaluation_id, target_revision, path, symbol, vuln_class,
                 detector_mode, rule_id, detector_rationale, state)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'candidate')
            ON CONFLICT (evaluation_id, fingerprint) DO UPDATE SET
                detector_rationale = EXCLUDED.detector_rationale,
                updated_at = now()
            RETURNING id
            """,
            evaluation_id, target_revision, path, symbol, vuln_class,
            detector_mode, rule_id, rationale,
        )
        return row["id"]

    async def add_citation(
        self,
        finding_id: uuid.UUID,
        evaluation_id: uuid.UUID,
        cite_path: str,
        cite_symbol: str,
        quoted_excerpt: str,
    ) -> uuid.UUID | None:
        """Inserts an evidence citation. Returns None if rejected by the gate."""
        try:
            row = await self._conn.fetchrow(
                """
                INSERT INTO evidence_citations
                    (finding_id, evaluation_id, cite_path, cite_symbol, quoted_excerpt)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                finding_id, evaluation_id, cite_path, cite_symbol, quoted_excerpt,
            )
            return row["id"]
        except asyncpg.exceptions.CheckViolationError as e:
            log.warning("citation_rejected", reason=str(e), finding_id=str(finding_id))
            return None

    async def set_verdict(
        self,
        finding_id: uuid.UUID,
        verdict: str,
        notes: str,
        severity: str | None = None,
    ) -> bool:
        """Sets verdict and flips survived_gate. Returns False if evidence gate rejects."""
        try:
            await self._conn.execute(
                """
                UPDATE findings SET
                    verdict = $2,
                    triager_notes = $3,
                    severity = $4,
                    state = 'triaged',
                    survived_gate = ($2 = 'true-positive'),
                    updated_at = now()
                WHERE id = $1
                """,
                finding_id, verdict, notes, severity,
            )
            return True
        except asyncpg.exceptions.CheckViolationError as e:
            log.warning("evidence_gate_rejected", finding_id=str(finding_id), reason=str(e))
            await self._conn.execute(
                "UPDATE findings SET state='rejected', triager_notes=$2 WHERE id=$1",
                finding_id, f"Rejected by evidence gate: {e}",
            )
            return False

    async def list_findings(
        self,
        evaluation_id: uuid.UUID,
        state: str | None = None,
        survived_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["evaluation_id = $1"]
        params: list[Any] = [evaluation_id]
        if state:
            clauses.append(f"state = ${len(params)+1}")
            params.append(state)
        if survived_only:
            clauses.append("survived_gate = true")
        rows = await self._conn.fetch(
            f"SELECT * FROM findings WHERE {' AND '.join(clauses)} ORDER BY created_at",
            *params,
        )
        return [dict(r) for r in rows]

    async def get_finding(self, finding_id: uuid.UUID) -> dict[str, Any] | None:
        row = await self._conn.fetchrow("SELECT * FROM findings WHERE id = $1", finding_id)
        return dict(row) if row else None

    async def list_citations(self, finding_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = await self._conn.fetch(
            "SELECT * FROM evidence_citations WHERE finding_id = $1",
            finding_id,
        )
        return [dict(r) for r in rows]

    # ── Exploit proofs (Principle VII) ─────────────────────────────────────

    async def record_exploit(
        self,
        finding_id: uuid.UUID,
        evaluation_id: uuid.UUID,
        poc_author_agent_id: uuid.UUID,
        runner_agent_id: uuid.UUID,
        artifact_uri: str,
        observed_impact: str,
        sandbox_log_uri: str,
    ) -> uuid.UUID | None:
        try:
            row = await self._conn.fetchrow(
                """
                INSERT INTO exploit_proofs
                    (finding_id, evaluation_id, poc_author_agent_id,
                     runner_agent_id, artifact_uri, observed_impact, sandbox_log_uri)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                finding_id, evaluation_id, poc_author_agent_id, runner_agent_id,
                artifact_uri, observed_impact, sandbox_log_uri,
            )
            await self._conn.execute(
                "UPDATE findings SET exploited = true, state='validated' WHERE id = $1",
                finding_id,
            )
            return row["id"]
        except asyncpg.exceptions.CheckViolationError as e:
            log.error("exploit_independence_violated", reason=str(e))
            return None

    # ── Coverage ────────────────────────────────────────────────────────────

    async def upsert_coverage(
        self, evaluation_id: uuid.UUID, dim: str, item_id: str, status: str
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO coverage_dimensions (evaluation_id, dim, item_id, status, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (evaluation_id, dim, item_id) DO UPDATE SET
                status = EXCLUDED.status,
                updated_at = now()
            """,
            evaluation_id, dim, item_id, status,
        )

    async def coverage_complete(self, evaluation_id: uuid.UUID) -> bool:
        # Principle VI: every dimension's items must be credibly_attempted.
        row = await self._conn.fetchrow(
            """
            SELECT count(*) FILTER (WHERE status <> 'credibly_attempted') AS pending,
                   count(*) AS total
              FROM coverage_dimensions
             WHERE evaluation_id = $1
            """,
            evaluation_id,
        )
        return bool(row and row["total"] > 0 and row["pending"] == 0)

    # ── Session logs (NFR-007) ─────────────────────────────────────────────

    async def log_session(
        self,
        evaluation_id: uuid.UUID,
        agent_id: uuid.UUID,
        role: str,
        event_type: str,
        payload: dict[str, Any],
        finding_id: uuid.UUID | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO session_logs
                (evaluation_id, agent_id, finding_id, role, event_type, payload, tokens_in, tokens_out)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            """,
            evaluation_id, agent_id, finding_id, role, event_type,
            json.dumps(payload), tokens_in, tokens_out,
        )


class Substrate:
    """Connection pool factory."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        self._pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=20)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    @asynccontextmanager
    async def conn(self) -> AsyncIterator[SubstrateConn]:
        assert self._pool, "Substrate not initialized"
        async with self._pool.acquire() as raw:
            yield SubstrateConn(raw)
