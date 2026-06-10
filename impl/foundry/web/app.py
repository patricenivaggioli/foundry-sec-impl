"""FastAPI app — read-only inspector for a Foundry Sec evaluation."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse


def create_app(dsn: str, config_path: str | None = None) -> FastAPI:
    app = FastAPI(title="Foundry Sec Inspector", version="0.1.0")
    state: dict[str, Any] = {
        "dsn": dsn,
        "pool": None,
        "config_path": config_path,
        "run_proc": None,        # asyncio.subprocess.Process or None
        "run_started_at": None,
        "run_log_path": None,
        "run_eval_id": None,
    }

    @app.on_event("startup")
    async def _startup() -> None:
        state["pool"] = await asyncpg.create_pool(dsn, min_size=1, max_size=8)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if state["pool"]:
            await state["pool"].close()

    async def fetch(q: str, *args: Any) -> list[dict[str, Any]]:
        async with state["pool"].acquire() as c:
            rows = await c.fetch(q, *args)
            return [dict(r) for r in rows]

    async def fetchrow(q: str, *args: Any) -> dict[str, Any] | None:
        async with state["pool"].acquire() as c:
            r = await c.fetchrow(q, *args)
            return dict(r) if r else None

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_HTML

    @app.get("/api/evaluations")
    async def list_evaluations() -> list[dict[str, Any]]:
        return await fetch(
            """
            SELECT e.id, e.name, e.target_path, e.target_revision, e.created_at,
              (SELECT count(*) FROM findings f WHERE f.evaluation_id=e.id) AS findings,
              (SELECT count(*) FROM findings f WHERE f.evaluation_id=e.id AND f.survived_gate=true) AS survived,
              (SELECT count(*) FROM exploit_proofs ep WHERE ep.evaluation_id=e.id) AS exploits,
              (SELECT count(*) FROM agents a WHERE a.evaluation_id=e.id) AS agents
              FROM evaluations e ORDER BY created_at DESC LIMIT 50
            """
        )

    @app.get("/api/evaluations/{evaluation_id}/summary")
    async def summary(evaluation_id: uuid.UUID) -> dict[str, Any]:
        ev = await fetchrow("SELECT * FROM evaluations WHERE id=$1", evaluation_id)
        if not ev:
            raise HTTPException(404, "Evaluation not found")
        ev["config"] = _maybe_json(ev.get("config"))
        q = await fetch(
            """
            SELECT task_kind, state, count(*) AS n FROM work_queue
             WHERE evaluation_id=$1 GROUP BY task_kind, state
             ORDER BY task_kind, state
            """,
            evaluation_id,
        )
        fstats = await fetch(
            """
            SELECT vuln_class, verdict, survived_gate, count(*) AS n FROM findings
             WHERE evaluation_id=$1 GROUP BY vuln_class, verdict, survived_gate
             ORDER BY vuln_class
            """,
            evaluation_id,
        )
        cite_stats = await fetchrow(
            """
            SELECT count(*) AS accepted, 0::bigint AS rejected
              FROM evidence_citations WHERE evaluation_id=$1
            """,
            evaluation_id,
        )
        return {"evaluation": ev, "queue": q, "findings": fstats, "citations": cite_stats}

    @app.get("/api/evaluations/{evaluation_id}/agents")
    async def agents(evaluation_id: uuid.UUID) -> list[dict[str, Any]]:
        return await fetch(
            """
            SELECT a.id, a.role, a.instance_index, a.state, a.pid,
                   a.last_heartbeat, a.started_at AS created_at,
                   EXTRACT(EPOCH FROM (now() - a.last_heartbeat))::int AS age_s,
                   (SELECT count(*) FROM work_queue w
                      WHERE w.claimed_by=a.id AND w.state='claimed') AS active_claims,
                   (SELECT count(*) FROM work_queue w
                      WHERE w.claimed_by=a.id AND w.state='done') AS completed
              FROM agents a WHERE a.evaluation_id=$1
             ORDER BY a.role, a.instance_index
            """,
            evaluation_id,
        )

    @app.get("/api/evaluations/{evaluation_id}/queue")
    async def queue(evaluation_id: uuid.UUID, limit: int = 200) -> list[dict[str, Any]]:
        return await fetch(
            """
            SELECT w.id, w.task_kind, w.state, w.priority, w.attempts, w.last_error,
                   w.created_at, w.updated_at, a.role AS claimed_by_role
              FROM work_queue w LEFT JOIN agents a ON a.id=w.claimed_by
             WHERE w.evaluation_id=$1 ORDER BY w.updated_at DESC LIMIT $2
            """,
            evaluation_id, limit,
        )

    @app.get("/api/evaluations/{evaluation_id}/findings")
    async def findings(
        evaluation_id: uuid.UUID,
        survived_only: bool = False,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses = ["evaluation_id=$1"]
        params: list[Any] = [evaluation_id]
        if survived_only:
            clauses.append("survived_gate=true")
        return await fetch(
            f"""
            SELECT f.id, f.path, f.symbol, f.vuln_class, f.detector_mode, f.rule_id,
                   f.verdict, f.severity, f.state, f.survived_gate, f.fingerprint,
                   f.created_at, f.updated_at,
                   (SELECT count(*) FROM evidence_citations c
                      WHERE c.finding_id=f.id) AS citations,
                   (SELECT count(*) FROM exploit_proofs ep WHERE ep.finding_id=f.id) AS exploits
              FROM findings f WHERE {' AND '.join(clauses)}
             ORDER BY f.survived_gate DESC, f.severity DESC NULLS LAST, f.created_at DESC
             LIMIT ${len(params)+1}
            """,
            *params, limit,
        )

    @app.get("/api/findings/{finding_id}")
    async def finding_detail(finding_id: uuid.UUID) -> dict[str, Any]:
        f = await fetchrow("SELECT * FROM findings WHERE id=$1", finding_id)
        if not f:
            raise HTTPException(404, "Finding not found")
        cites = await fetch(
            "SELECT * FROM evidence_citations WHERE finding_id=$1 ORDER BY created_at",
            finding_id,
        )
        exploits = await fetch(
            "SELECT * FROM exploit_proofs WHERE finding_id=$1 ORDER BY created_at",
            finding_id,
        )
        sym = await fetchrow(
            """
            SELECT path, symbol, body, start_line, end_line FROM code_symbols
             WHERE evaluation_id=$1 AND path=$2 AND symbol=$3
            """,
            f["evaluation_id"], f["path"], f["symbol"],
        )
        return {"finding": f, "citations": cites, "exploits": exploits, "symbol": sym}

    @app.get("/api/evaluations/{evaluation_id}/timeline")
    async def timeline(
        evaluation_id: uuid.UUID,
        limit: int = 200,
        finding_id: uuid.UUID | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        clauses = ["evaluation_id=$1"]
        params: list[Any] = [evaluation_id]
        if finding_id:
            clauses.append(f"finding_id=${len(params)+1}")
            params.append(finding_id)
        rows = await fetch(
            f"""
            SELECT id, created_at AS timestamp, role, event_type, payload, finding_id,
                   tokens_in, tokens_out
              FROM session_logs WHERE {' AND '.join(clauses)}
             ORDER BY created_at DESC LIMIT ${len(params)+1}
            """,
            *params, limit,
        )
        for r in rows:
            r["payload"] = _maybe_json(r["payload"])
        return rows

    @app.get("/api/evaluations/{evaluation_id}/trace")
    async def trace(evaluation_id: uuid.UUID) -> dict[str, Any]:
        nodes = await fetch(
            """
            SELECT a.role, a.instance_index, a.state, a.pid,
                   EXTRACT(EPOCH FROM (now() - a.last_heartbeat))::int AS age_s,
                   (SELECT count(*) FROM work_queue w
                      WHERE w.claimed_by=a.id AND w.state='done') AS completed,
                   (SELECT count(*) FROM session_logs sl
                      WHERE sl.agent_id=a.id) AS events,
                   (SELECT coalesce(sum(tokens_in::bigint + tokens_out::bigint), 0)
                      FROM session_logs sl WHERE sl.agent_id=a.id) AS tokens
              FROM agents a WHERE a.evaluation_id=$1
             ORDER BY a.role, a.instance_index
            """,
            evaluation_id,
        )
        # Synthesize an orchestrator node from work_queue task counts. The
        # lifecycle orchestrator runs in-process from the CLI and never
        # registers in agents/session_logs, so we project its activity from
        # the kick-off task kinds it enqueued.
        orch_row = await fetchrow(
            """
            SELECT
              (SELECT count(*) FROM work_queue WHERE evaluation_id=$1
                 AND task_kind IN ('index','cartograph_doc','detect_rule','detect_explore',
                                   'coverage_tick','validate','report')
                 AND state='done')::int AS completed,
              (SELECT count(*) FROM work_queue WHERE evaluation_id=$1)::int AS total,
              (SELECT EXTRACT(EPOCH FROM (now() - min(created_at)))::int
                 FROM work_queue WHERE evaluation_id=$1) AS age_s
            """,
            evaluation_id,
        ) or {}
        synthesized = [
            {
                "role": "orchestrator",
                "instance_index": 0,
                "state": "running",
                "pid": None,
                "age_s": int(orch_row.get("age_s") or 0),
                "completed": int(orch_row.get("completed") or 0),
                "events": int(orch_row.get("total") or 0),
                "tokens": 0,
            }
        ]
        nodes = synthesized + list(nodes)
        edges = await fetch(
            """
            WITH first_touch AS (
                SELECT finding_id, role, min(created_at) AS first_at
                  FROM session_logs
                 WHERE evaluation_id=$1 AND finding_id IS NOT NULL
                 GROUP BY finding_id, role
            ),
            traces AS (
                SELECT ft1.role AS from_role, ft2.role AS to_role,
                       count(DISTINCT ft1.finding_id) AS weight
                  FROM first_touch ft1
                  JOIN first_touch ft2
                    ON ft1.finding_id = ft2.finding_id
                   AND ft1.role <> ft2.role
                   AND ft1.first_at < ft2.first_at
                 GROUP BY ft1.role, ft2.role
            ),
            -- Pipeline edges seeded from work_queue task_kind counts so the
            -- canonical flow is always visible even if session_logs are sparse.
            seeds AS (
                SELECT 'indexer'::text AS from_role, 'cartographer'::text AS to_role,
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='cartograph_doc' AND state='done')::bigint AS weight
                UNION ALL
                SELECT 'cartographer', 'detector',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind IN ('detect_rule','detect_explore') AND state='done')::bigint
                UNION ALL
                SELECT 'detector', 'triager',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='triage' AND state='done')::bigint
                UNION ALL
                SELECT 'triager', 'validator',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='validate' AND state='done')::bigint
                UNION ALL
                SELECT 'validator', 'reporter',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='report' AND state='done')::bigint
                UNION ALL
                SELECT 'coverage_guide', 'detector',
                       (SELECT count(*) FROM coverage_dimensions WHERE evaluation_id=$1 AND status='credibly_attempted')::bigint
                UNION ALL
                -- Orchestrator dispatches: one synthetic edge per phase it kicked.
                SELECT 'orchestrator', 'indexer',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='index' AND state='done')::bigint
                UNION ALL
                SELECT 'orchestrator', 'cartographer',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='cartograph_doc' AND state='done')::bigint
                UNION ALL
                SELECT 'orchestrator', 'detector',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind IN ('detect_rule','detect_explore') AND state='done')::bigint
                UNION ALL
                SELECT 'orchestrator', 'coverage_guide',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='coverage_tick' AND state='done')::bigint
                UNION ALL
                SELECT 'orchestrator', 'validator',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='validate' AND state='done')::bigint
                UNION ALL
                SELECT 'orchestrator', 'reporter',
                       (SELECT count(*) FROM work_queue WHERE evaluation_id=$1 AND task_kind='report' AND state='done')::bigint
            )
            SELECT from_role, to_role, max(weight)::bigint AS weight
              FROM (SELECT * FROM traces UNION ALL SELECT * FROM seeds) u
             WHERE weight > 0
             GROUP BY from_role, to_role
             ORDER BY weight DESC
            """,
            evaluation_id,
        )
        return {"nodes": nodes, "edges": edges}

    @app.get("/api/evaluations/{evaluation_id}/security_map")
    async def security_map(evaluation_id: uuid.UUID) -> dict[str, Any]:
        rows = await fetch(
            "SELECT doc_kind, content, is_fallback, updated_at "
            "FROM security_map WHERE evaluation_id=$1 ORDER BY doc_kind",
            evaluation_id,
        )
        return {"docs": [dict(r) for r in rows]}

    @app.get("/api/evaluations/{evaluation_id}/coverage")
    async def coverage(evaluation_id: uuid.UUID) -> dict[str, Any]:
        rows = await fetch(
            "SELECT dim, item_id, status, updated_at "
            "FROM coverage_dimensions WHERE evaluation_id=$1 "
            "ORDER BY dim, item_id",
            evaluation_id,
        )
        by_dim: dict[str, list[dict[str, Any]]] = {}
        totals: dict[str, dict[str, int]] = {}
        for r in rows:
            dim = r["dim"]
            by_dim.setdefault(dim, []).append({
                "item_id": r["item_id"],
                "status": r["status"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            })
            t = totals.setdefault(dim, {"total": 0, "credibly_attempted": 0,
                                        "in_progress": 0, "untouched": 0})
            t["total"] += 1
            t[r["status"]] = t.get(r["status"], 0) + 1
        tick_row = await fetchrow(
            "SELECT count(*) AS n FROM work_queue "
            "WHERE evaluation_id=$1 AND task_kind='coverage_tick' AND state='done'",
            evaluation_id,
        )
        ticks = int(tick_row["n"]) if tick_row else 0
        return {"by_dim": by_dim, "totals": totals, "ticks": ticks}

    @app.get("/api/evaluations/{evaluation_id}/index")
    async def index_view(evaluation_id: uuid.UUID) -> dict[str, Any]:
        gate_row = await fetchrow(
            "SELECT queryable, released_at FROM index_gate WHERE evaluation_id=$1",
            evaluation_id,
        )
        files = await fetch(
            "SELECT path, count(*) AS symbols, "
            "       sum(CASE WHEN kind='method' THEN 1 ELSE 0 END) AS methods, "
            "       sum(CASE WHEN kind='function' THEN 1 ELSE 0 END) AS functions, "
            "       max(end_line) AS last_line "
            "FROM code_symbols WHERE evaluation_id=$1 "
            "GROUP BY path ORDER BY path",
            evaluation_id,
        )
        symbols = await fetch(
            "SELECT path, symbol, kind, start_line, end_line "
            "FROM code_symbols WHERE evaluation_id=$1 "
            "ORDER BY path, start_line",
            evaluation_id,
        )
        edges = await fetch(
            "SELECT caller_path, caller_symbol, callee_symbol "
            "FROM call_edges WHERE evaluation_id=$1 "
            "ORDER BY caller_path, caller_symbol, callee_symbol",
            evaluation_id,
        )
        return {
            "gate": dict(gate_row) if gate_row else None,
            "files": [dict(r) for r in files],
            "symbols": [dict(r) for r in symbols],
            "edges": [dict(r) for r in edges],
            "totals": {
                "files": len(files),
                "symbols": len(symbols),
                "edges": len(edges),
            },
        }

    @app.get("/api/evaluations/{evaluation_id}/index/symbol")
    async def index_symbol(
        evaluation_id: uuid.UUID, path: str, symbol: str
    ) -> dict[str, Any]:
        row = await fetchrow(
            "SELECT path, symbol, kind, start_line, end_line, body "
            "FROM code_symbols WHERE evaluation_id=$1 AND path=$2 AND symbol=$3",
            evaluation_id, path, symbol,
        )
        if not row:
            raise HTTPException(404, "symbol not found")
        return dict(row)

    async def _report_dir(evaluation_id: uuid.UUID) -> Path:
        row = await fetchrow(
            "SELECT task_payload FROM work_queue "
            "WHERE evaluation_id=$1 AND task_kind='report' "
            "ORDER BY updated_at DESC LIMIT 1",
            evaluation_id,
        )
        out = "output"
        if row:
            payload = _maybe_json(row["task_payload"])
            if isinstance(payload, dict):
                out = payload.get("output_dir") or out
        return Path(out)

    @app.get("/api/evaluations/{evaluation_id}/report")
    async def report_meta(evaluation_id: uuid.UUID) -> dict[str, Any]:
        d = await _report_dir(evaluation_id)
        files = []
        for name, kind in [("report.md", "markdown"), ("findings.sarif", "sarif")]:
            p = d / name
            if p.exists():
                st = p.stat()
                files.append({
                    "name": name,
                    "kind": kind,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
        return {"output_dir": str(d), "files": files}

    @app.get("/api/evaluations/{evaluation_id}/report/{filename}")
    async def report_file(evaluation_id: uuid.UUID, filename: str):
        if filename not in ("report.md", "findings.sarif"):
            raise HTTPException(404, "Unknown report file")
        d = await _report_dir(evaluation_id)
        p = d / filename
        if not p.exists():
            raise HTTPException(404, f"{filename} not found in {d}")
        return PlainTextResponse(p.read_text(encoding="utf-8"))

    @app.get("/api/evaluations/{evaluation_id}/role_tasks")
    async def role_tasks(
        evaluation_id: uuid.UUID,
        role: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        agent_ids = await fetch(
            "SELECT id FROM agents WHERE evaluation_id=$1 AND role=$2",
            evaluation_id, role,
        )
        ids = [a["id"] for a in agent_ids]
        tasks = await fetch(
            """
            SELECT w.id, w.task_kind, w.task_payload, w.state, w.priority,
                   w.attempts, w.last_error, w.created_at, w.updated_at,
                   a.role AS claimed_by_role, a.instance_index
              FROM work_queue w LEFT JOIN agents a ON a.id=w.claimed_by
             WHERE w.evaluation_id=$1
               AND ($3 = 'orchestrator'
                    OR w.claimed_by = ANY($2::uuid[])
                    OR ($3 = 'indexer'        AND w.task_kind='index')
                    OR ($3 = 'cartographer'   AND w.task_kind='cartograph_doc')
                    OR ($3 = 'detector'       AND w.task_kind IN ('detect_rule','detect_explore'))
                    OR ($3 = 'triager'        AND w.task_kind='triage')
                    OR ($3 = 'coverage_guide' AND w.task_kind='coverage_tick')
                    OR ($3 = 'validator'      AND w.task_kind='validate')
                    OR ($3 = 'reporter'       AND w.task_kind='report'))
             ORDER BY w.updated_at DESC LIMIT $4
            """,
            evaluation_id, ids, role, limit,
        )
        for t in tasks:
            t["task_payload"] = _maybe_json(t["task_payload"])
        # Status counts for summary
        counts = await fetchrow(
            """
            SELECT count(*) FILTER (WHERE state='done')    AS done,
                   count(*) FILTER (WHERE state='ready')   AS ready,
                   count(*) FILTER (WHERE state='claimed') AS claimed,
                   count(*) FILTER (WHERE state='failed')  AS failed
              FROM work_queue
             WHERE evaluation_id=$1 AND (
                 $3='orchestrator'
                 OR claimed_by = ANY($2::uuid[])
                 OR ($3='indexer'        AND task_kind='index')
                 OR ($3='cartographer'   AND task_kind='cartograph_doc')
                 OR ($3='detector'       AND task_kind IN ('detect_rule','detect_explore'))
                 OR ($3='triager'        AND task_kind='triage')
                 OR ($3='coverage_guide' AND task_kind='coverage_tick')
                 OR ($3='validator'      AND task_kind='validate')
                 OR ($3='reporter'       AND task_kind='report')
             )
            """,
            evaluation_id, ids, role,
        )
        return {"role": role, "counts": counts or {}, "tasks": tasks}

    # ── Run a new evaluation as a background subprocess ──────────────────────
    EVAL_ID_RE = re.compile(r"evaluation_created.*?id=([0-9a-f-]{36})", re.IGNORECASE)

    def _proc_status() -> dict[str, Any]:
        proc = state.get("run_proc")
        running = proc is not None and proc.returncode is None
        if proc is not None and proc.returncode is not None:
            status = "succeeded" if proc.returncode == 0 else "failed"
        elif running:
            status = "running"
        else:
            status = "idle"
        return {
            "status": status,
            "running": running,
            "returncode": None if running else (proc.returncode if proc else None),
            "started_at": state.get("run_started_at"),
            "log_path": state.get("run_log_path"),
            "evaluation_id": state.get("run_eval_id"),
        }

    @app.post("/api/run", status_code=202)
    async def start_run() -> dict[str, Any]:
        if not state.get("config_path"):
            raise HTTPException(400, "Server was launched without --config; cannot run.")
        proc = state.get("run_proc")
        if proc is not None and proc.returncode is None:
            raise HTTPException(409, "An evaluation is already running.")

        log_path = Path(tempfile.gettempdir()) / f"foundry-run-{int(time.time())}.log"
        log_fp = log_path.open("wb")
        env = os.environ.copy()
        # Ensure the substrate is reachable from the subprocess.
        env.setdefault("FOUNDRY_DSN", state["dsn"])
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "foundry.cli", "run",
            "--config", state["config_path"],
            stdin=asyncio.subprocess.DEVNULL,
            stdout=log_fp,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        state["run_proc"] = proc
        state["run_started_at"] = time.time()
        state["run_log_path"] = str(log_path)
        state["run_eval_id"] = None

        async def _watch() -> None:
            await proc.wait()
            log_fp.close()
            # Try to extract the evaluation_id from the log.
            try:
                text = log_path.read_text(errors="replace")
                m = EVAL_ID_RE.search(text)
                if m:
                    state["run_eval_id"] = m.group(1)
            except Exception:
                pass

        asyncio.create_task(_watch())
        return _proc_status()

    @app.get("/api/run/status")
    async def run_status() -> dict[str, Any]:
        return _proc_status()

    @app.get("/api/run/log")
    async def run_log(tail: int = 200) -> dict[str, Any]:
        lp = state.get("run_log_path")
        if not lp:
            return {"lines": []}
        try:
            text = Path(lp).read_text(errors="replace")
        except FileNotFoundError:
            return {"lines": []}
        lines = text.splitlines()
        return {"lines": lines[-tail:]}

    return app


def _maybe_json(v: Any) -> Any:
    if v is None or not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except Exception:
        return v


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Foundry Sec — Inspector</title>
<style>
  :root {
    --bg: #0b0d10; --panel: #14181d; --panel-2: #1a1f26; --border: #2a313b;
    --text: #e7ecf2; --muted: #8b96a4; --accent: #5dd6ff; --accent-2: #7df0a8;
    --warn: #ffb86b; --bad: #ff6f8b; --ok: #7df0a8; --neutral: #8b96a4;
    --mono: ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; background: var(--bg); color: var(--text);
    font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
  a { color: var(--accent); text-decoration: none; }
  header { display: flex; align-items: center; gap: 16px; padding: 10px 18px;
    background: var(--panel); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 5; }
  header h1 { font-size: 14px; font-weight: 600; margin: 0; letter-spacing: 0.4px; }
  header h1 .dot { color: var(--accent); }
  header .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-2);
    box-shadow: 0 0 0 0 rgba(125,240,168,.6); animation: pulse 2s infinite; }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(125,240,168,.55); }
    70% { box-shadow: 0 0 0 8px rgba(125,240,168,0); }
    100% { box-shadow: 0 0 0 0 rgba(125,240,168,0); }
  }
  header select { background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
    padding: 6px 10px; border-radius: 4px; font-size: 13px; min-width: 360px; }
  header .run-btn { background: var(--panel-2); color: var(--accent); border: 1px solid var(--accent);
    padding: 6px 12px; border-radius: 4px; font-size: 12.5px; font-family: var(--mono);
    cursor: pointer; transition: background .15s, color .15s; }
  header .run-btn:hover:not(:disabled) { background: var(--accent); color: var(--bg); }
  header .run-btn:disabled { opacity: 0.45; cursor: not-allowed; border-color: var(--border); color: var(--muted); }
  header .run-btn.running { color: var(--warn, #ffb86b); border-color: var(--warn, #ffb86b); }
  header .run-status { font-family: var(--mono); font-size: 11.5px; color: var(--muted); }
  header .run-status.ok  { color: #7df0a8; }
  header .run-status.bad { color: var(--bad); }
  header .run-status .spinner { display: inline-block; width: 10px; height: 10px;
    border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%;
    animation: spin .9s linear infinite; vertical-align: -1px; margin-right: 4px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  header .spacer { flex: 1; }
  header .meta { color: var(--muted); font-size: 12px; font-family: var(--mono); }
  .grid { display: grid; grid-template-columns: 320px 1fr 460px; gap: 12px; padding: 12px; height: calc(100vh - 90px); }
  /* ── Tabs ── */
  .tabs { display: flex; gap: 0; padding: 0 18px; background: var(--panel); border-bottom: 1px solid var(--border); }
  .tab-btn { padding: 8px 18px; font-size: 13px; cursor: pointer; border: none; background: none;
    border-bottom: 2px solid transparent; color: var(--muted); transition: color .15s; }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
  /* ── Tracing pane ── */
  #tracingView { display: none; position: relative; height: calc(100vh - 90px); padding: 12px; }
  #traceGraph { width: 100%; height: 100%; }
  .node-label { font-family: var(--mono); font-size: 11px; fill: var(--text); pointer-events: none; }
  .node-sub { font-family: var(--mono); font-size: 10px; fill: var(--muted); pointer-events: none; }
  .edge-label { font-family: var(--mono); font-size: 10px; fill: var(--muted); pointer-events: none; }
  #tracePanel { position: absolute; right: 24px; top: 12px; width: 360px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 6px; padding: 14px; font-size: 12px;
    display: none; max-height: calc(100vh - 130px); overflow: auto; box-shadow: 0 8px 28px rgba(0,0,0,.4); }
  #tracePanel .panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  #tracePanel .panel-head h3 { margin: 0; font-size: 13px; font-family: var(--mono); color: var(--accent); }
  #tracePanel .panel-close { background: none; border: none; color: var(--muted); font-size: 18px; line-height: 1;
    cursor: pointer; padding: 0 2px; transition: color .15s; }
  #tracePanel .panel-close:hover { color: var(--text); }
  #tracePanel .kv { display: flex; justify-content: space-between; padding: 3px 0;
    border-bottom: 1px dashed var(--border); }
  #tracePanel .kv .k { color: var(--muted); }
  #tracePanel .kv .v { font-family: var(--mono); }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
    display: flex; flex-direction: column; min-height: 0; }
  .card h2 { margin: 0; padding: 9px 12px; font-size: 12px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.7px; color: var(--muted); border-bottom: 1px solid var(--border);
    background: var(--panel-2); display: flex; align-items: center; gap: 8px; }
  .card h2 .badge { background: var(--bg); border: 1px solid var(--border); padding: 1px 8px;
    border-radius: 10px; font-family: var(--mono); font-size: 11px; color: var(--text); text-transform: none;
    letter-spacing: 0; }
  .card .body { overflow: auto; padding: 8px; flex: 1; min-height: 0; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
  tr:hover td { background: var(--panel-2); cursor: pointer; }
  tr.selected td { background: rgba(93, 214, 255, 0.08); }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px;
    font-family: var(--mono); border: 1px solid var(--border); background: var(--panel-2); }
  .pill.ok { color: var(--ok); border-color: rgba(125,240,168,.3); }
  .pill.bad { color: var(--bad); border-color: rgba(255,111,139,.3); }
  .pill.warn { color: var(--warn); border-color: rgba(255,184,107,.3); }
  .pill.accent { color: var(--accent); border-color: rgba(93,214,255,.3); }
  .pill.neutral { color: var(--neutral); }
  .mono { font-family: var(--mono); }
  .small { font-size: 11.5px; color: var(--muted); }
  .stat-row { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 0; }
  .stat { background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px;
    min-width: 100px; }
  .stat .v { font-size: 16px; font-weight: 600; }
  .stat .l { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  pre.code { margin: 0; padding: 10px; background: #06080a; border: 1px solid var(--border);
    border-radius: 4px; overflow: auto; font-family: var(--mono); font-size: 12px; line-height: 1.4;
    white-space: pre-wrap; }
  pre.code .hl { background: rgba(255,184,107,.18); border-radius: 2px; }
  .citation { padding: 8px 10px; border-left: 3px solid var(--ok); background: rgba(125,240,168,.05);
    margin-bottom: 6px; border-radius: 0 4px 4px 0; }
  .citation.bad { border-left-color: var(--bad); background: rgba(255,111,139,.05); }
  .citation .who { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
  .citation .ex { font-family: var(--mono); font-size: 12px; word-break: break-word; white-space: pre-wrap; }
  .timeline-row { display: flex; gap: 10px; padding: 5px 0; border-bottom: 1px dashed var(--border); font-size: 12px; }
  .timeline-row .t { color: var(--muted); font-family: var(--mono); white-space: nowrap; min-width: 80px; }
  .timeline-row .r { font-family: var(--mono); color: var(--accent); white-space: nowrap; min-width: 110px; }
  .empty { padding: 24px; text-align: center; color: var(--muted); }
  .legend { font-size: 11px; color: var(--muted); padding: 4px 12px 8px; }
  details > summary { cursor: pointer; padding: 4px 0; color: var(--muted); font-size: 11.5px; }
  details > summary::-webkit-details-marker { color: var(--muted); }
  .toolbar { display: flex; gap: 6px; padding: 6px 8px; border-bottom: 1px solid var(--border); background: var(--panel-2); }
  .toolbar input[type="checkbox"] { accent-color: var(--accent); }
  .toolbar label { font-size: 12px; color: var(--muted); cursor: pointer; }
</style>
<style>
  /* n8n-flavoured workflow canvas */
  #workflowView { display: none; position: relative; height: calc(100vh - 90px);
    background: #1a1d24;
    background-image: radial-gradient(circle, #2c313a 1px, transparent 1px);
    background-size: 18px 18px; }
  #workflowView .vue-flow__node {
    border-radius: 12px; background: #2d313b; border: 1.5px solid rgba(255,255,255,.08);
    color: var(--text); font-family: var(--mono); padding: 0; min-width: 180px;
    box-shadow: 0 4px 14px rgba(0,0,0,.35); transition: border-color .18s, transform .18s; }
  #workflowView .vue-flow__node.selected,
  #workflowView .vue-flow__node:hover { border-color: var(--accent); transform: translateY(-1px); }
  #workflowView .n8n-node-card { display: grid; grid-template-columns: 60px 1fr; align-items: stretch;
    width: 100%; border-radius: 10px; overflow: hidden; }
  #workflowView .n8n-node-icon { display: flex; align-items: center; justify-content: center;
    font-size: 26px; background: var(--n8n-color, #5dd6ff); color: #fff;
    border-right: 1.5px solid rgba(0,0,0,.2); }
  #workflowView .n8n-node-body { padding: 10px 12px; min-width: 0; }
  #workflowView .n8n-node-title { font-weight: 600; font-size: 13px; color: var(--text);
    text-transform: capitalize; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #workflowView .n8n-node-sub { font-size: 11px; color: var(--muted); margin-top: 3px; font-family: var(--mono); }
  #workflowView .n8n-node-pills { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
  #workflowView .n8n-node-pill { font-size: 10px; padding: 1px 6px; border-radius: 9px;
    background: rgba(93,214,255,.12); color: var(--accent); border: 1px solid rgba(93,214,255,.3); }
  #workflowView .n8n-node-pill.warn { background: rgba(255,184,107,.12);
    color: #ffb86b; border-color: rgba(255,184,107,.3); }
  #workflowView .vue-flow__edge-path { stroke: #6e7484; stroke-width: 2; }
  #workflowView .vue-flow__edge.selected .vue-flow__edge-path,
  #workflowView .vue-flow__edge:hover .vue-flow__edge-path { stroke: var(--accent); stroke-width: 2.5; }
  #workflowView .vue-flow__edge-text { fill: var(--muted); font-family: var(--mono); font-size: 10px; }
  #workflowView .vue-flow__edge-textbg { fill: #1a1d24; }
  #workflowView .vue-flow__handle { width: 9px; height: 9px; background: #6e7484;
    border: 1.5px solid #1a1d24; }
  #workflowView .vue-flow__controls { background: #2d313b; border: 1px solid rgba(255,255,255,.08);
    border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,.3); }
  #workflowView .vue-flow__controls-button { background: #2d313b; border: none;
    border-bottom: 1px solid rgba(255,255,255,.06); color: var(--text); fill: var(--text); }
  #workflowView .vue-flow__controls-button:hover { background: #3a3f4a; }
  #workflowView .vue-flow__minimap { background: #14181d; border: 1px solid rgba(255,255,255,.08);
    border-radius: 6px; }
  #wfPanel { position: absolute; right: 24px; top: 12px; width: 360px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 6px; padding: 14px; font-size: 12px;
    display: none; max-height: calc(100vh - 130px); overflow: auto;
    box-shadow: 0 8px 28px rgba(0,0,0,.4); z-index: 10; }
  #wfPanel .panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  #wfPanel .panel-head h3 { margin: 0; font-size: 13px; font-family: var(--mono); color: var(--accent); }
  #wfPanel .panel-close { background: none; border: none; color: var(--muted); font-size: 18px;
    line-height: 1; cursor: pointer; padding: 0 2px; }
  #wfPanel .panel-close:hover { color: var(--text); }
  #wfPanel .kv { display: flex; justify-content: space-between; padding: 3px 0;
    border-bottom: 1px dashed var(--border); }
  #wfPanel .kv .k { color: var(--muted); }
  #wfPanel .kv .v { font-family: var(--mono); }
  /* Doc links in side panel */
  .doc-link { display: block; padding: 4px 8px; margin: 2px 0; border-radius: 4px;
    color: var(--accent); cursor: pointer; font-family: var(--mono); font-size: 11.5px;
    text-decoration: none; border: 1px solid transparent; }
  .doc-link:hover { background: rgba(93,214,255,.08); border-color: rgba(93,214,255,.25); }
  .doc-link .doc-fallback { color: var(--muted); font-size: 10px; margin-left: 6px; }
  /* Markdown modal */
  #docModal { position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1000;
    display: none; align-items: center; justify-content: center; padding: 40px; }
  #docModal.active { display: flex; }
  #docModal .modal-box { background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; max-width: 880px; width: 100%; max-height: 100%;
    display: flex; flex-direction: column; box-shadow: 0 12px 48px rgba(0,0,0,.5); }
  #docModal .modal-head { display: flex; align-items: center; justify-content: space-between;
    padding: 12px 18px; border-bottom: 1px solid var(--border); }
  #docModal .modal-head h3 { margin: 0; font-size: 14px; font-family: var(--mono);
    color: var(--accent); text-transform: capitalize; }
  #docModal .modal-head .close { background: none; border: none; color: var(--muted);
    font-size: 22px; line-height: 1; cursor: pointer; padding: 0 4px; }
  #docModal .modal-head .close:hover { color: var(--text); }
  #docModal .modal-body { padding: 18px 24px; overflow: auto; font-size: 13px;
    line-height: 1.6; color: var(--text); }
  #docModal .modal-body h1, #docModal .modal-body h2, #docModal .modal-body h3 {
    color: var(--accent); margin-top: 1.2em; margin-bottom: 0.5em; }
  #docModal .modal-body h1 { font-size: 20px; }
  #docModal .modal-body h2 { font-size: 17px; }
  #docModal .modal-body h3 { font-size: 14px; }
  #docModal .modal-body p { margin: 0.6em 0; }
  #docModal .modal-body ul, #docModal .modal-body ol { margin: 0.6em 0; padding-left: 22px; }
  #docModal .modal-body li { margin: 0.2em 0; }
  #docModal .modal-body code { background: var(--panel-2); padding: 1px 5px;
    border-radius: 3px; font-family: var(--mono); font-size: 12px; color: #ffb86b; }
  #docModal .modal-body pre { background: var(--panel-2); padding: 10px 14px;
    border-radius: 4px; overflow-x: auto; border: 1px solid var(--border); }
  #docModal .modal-body pre code { background: none; padding: 0; color: var(--text); }
  #docModal .modal-body strong { color: var(--text); font-weight: 600; }
  #docModal .modal-body blockquote { border-left: 3px solid var(--accent);
    margin: 0.6em 0; padding: 4px 12px; color: var(--muted); }
  #docModal .modal-body table { border-collapse: collapse; margin: 0.8em 0; }
  #docModal .modal-body th, #docModal .modal-body td { border: 1px solid var(--border);
    padding: 4px 10px; text-align: left; }
  #docModal .modal-foot { padding: 8px 18px; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 11px; font-family: var(--mono); }

  /* Graph modal — fullscreen Vue Flow viewer */
  #graphModal { position: fixed; inset: 0; background: rgba(0,0,0,.7); z-index: 1001;
    display: none; align-items: stretch; justify-content: stretch; padding: 24px; }
  #graphModal.active { display: flex; }
  #graphModal .graph-modal-box { background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #graphModal .modal-head { display: flex; align-items: center; justify-content: space-between;
    padding: 10px 18px; border-bottom: 1px solid var(--border); }
  #graphModal .modal-head h3 { margin: 0; font-size: 14px; font-family: var(--mono); }
  #graphModal .close { background: none; border: none; color: var(--muted);
    font-size: 22px; cursor: pointer; line-height: 1; padding: 0 4px; }
  #graphModal .close:hover { color: var(--text); }
  #graphModal .modal-foot { padding: 6px 14px; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 11px; font-family: var(--mono); }
  /* Custom call-graph node styling */
  .cg-node { background: var(--panel-2, #1c2128); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 10px; min-width: 140px; max-width: 240px;
    font-family: var(--mono); font-size: 11px; color: var(--text); }
  .cg-node.internal { border-color: #2fb67c; box-shadow: 0 0 0 1px rgba(47,182,124,.25); }
  .cg-node.external { border-color: #ff965a; opacity: 0.92; }
  .cg-node .cg-kind { font-size: 9px; color: var(--muted); text-transform: uppercase;
    letter-spacing: .5px; }
  .cg-node .cg-name { font-weight: 600; word-break: break-all; }
  .cg-node .cg-path { font-size: 10px; color: var(--muted); margin-top: 2px; word-break: break-all; }
</style>
<link rel="stylesheet" href="https://esm.sh/@vue-flow/core@1.42.1/dist/style.css">
<link rel="stylesheet" href="https://esm.sh/@vue-flow/core@1.42.1/dist/theme-default.css">
<link rel="stylesheet" href="https://esm.sh/@vue-flow/controls@1.1.2/dist/style.css">
<link rel="stylesheet" href="https://esm.sh/@vue-flow/minimap@1.5.0/dist/style.css">
<script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
<header>
  <h1>foundry<span class="dot">.</span>sec <span class="small mono" style="color:var(--muted)">inspector</span></h1>
  <span class="pulse" id="pulse" title="Live"></span>
  <select id="evalSelect"></select>
  <button id="runBtn" class="run-btn" title="Run a new evaluation with the current config">▶ Run new evaluation</button>
  <span id="runStatus" class="run-status"></span>
  <span class="spacer"></span>
  <span class="meta" id="metaStrip">—</span>
</header>

<nav class="tabs">
  <button class="tab-btn active" data-tab="pipeline">Pipeline</button>
  <button class="tab-btn" data-tab="tracing">Tracing</button>
  <button class="tab-btn" data-tab="workflow">Workflow</button>
</nav>

<div id="pipelineView" class="grid">
  <div class="card">
    <h2>Fleet <span class="badge" id="agentCount">0</span></h2>
    <div class="body" id="agentsBody" style="max-height:45%"></div>
    <h2>Work queue <span class="badge" id="queueCount">0</span></h2>
    <div class="body" id="queueBody"></div>
  </div>

  <div class="card">
    <h2>Findings <span class="badge" id="findingsCount">0</span></h2>
    <div class="toolbar">
      <input type="checkbox" id="survivedOnly" />
      <label for="survivedOnly">Show only survivors (passed evidence gate)</label>
    </div>
    <div class="body" id="findingsBody"></div>
  </div>

  <div class="card">
    <h2 id="detailTitle">Detail</h2>
    <div class="body" id="detailBody"><div class="empty">Select a finding to inspect.</div></div>
  </div>
</div>

<div id="tracingView" style="position:relative">
  <svg id="traceGraph"></svg>
  <div id="tracePanel"></div>
</div>

<div id="workflowView">
  <div id="vueflowRoot" style="width:100%;height:100%;position:relative"></div>
  <div id="wfPanel"></div>
</div>

<div id="docModal" onclick="if(event.target===this)closeDocModal()">
  <div class="modal-box">
    <div class="modal-head">
      <h3 id="docModalTitle">Document</h3>
      <button class="close" onclick="closeDocModal()" title="Close">×</button>
    </div>
    <div class="modal-body" id="docModalBody"></div>
    <div class="modal-foot" id="docModalFoot"></div>
  </div>
</div>

<div id="graphModal" onclick="if(event.target===this)closeGraphModal()">
  <div class="graph-modal-box">
    <div class="modal-head">
      <h3 id="graphModalTitle">Call graph</h3>
      <div style="display:flex;gap:10px;align-items:center">
        <label class="small" style="color:var(--muted);display:flex;align-items:center;gap:5px;cursor:pointer">
          <input type="checkbox" id="graphInternalOnly"> internal only
        </label>
        <button class="close" onclick="closeGraphModal()" title="Close">×</button>
      </div>
    </div>
    <div id="graphFlowRoot" style="flex:1;min-height:0"></div>
    <div class="modal-foot" id="graphModalFoot"></div>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const escape = (s) => (s ?? "").toString().replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const ago = (iso) => {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return Math.round(d) + "s";
  if (d < 3600) return Math.round(d / 60) + "m";
  if (d < 86400) return Math.round(d / 3600) + "h";
  return Math.round(d / 86400) + "d";
};
const sevPill = (s) => s ? `<span class="pill ${s==='critical'||s==='high'?'bad':s==='medium'?'warn':'neutral'}">${s}</span>` : '<span class="pill neutral">—</span>';
const verdictPill = (v) => {
  if (!v) return '<span class="pill neutral">candidate</span>';
  if (v === 'true-positive') return '<span class="pill bad">true-positive</span>';
  if (v === 'false-positive') return '<span class="pill ok">false-positive</span>';
  return `<span class="pill warn">${v}</span>`;
};

let currentEval = null;
window.currentEval = null;
let selectedFinding = null;

async function jget(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

async function loadEvals() {
  const evals = await jget('/api/evaluations');
  const sel = $('evalSelect');
  const prev = sel.value;
  sel.innerHTML = evals.map(e =>
    `<option value="${e.id}">${escape(e.name)} · ${escape(e.target_revision)} · ${e.findings} findings · ${e.survived} survivors · ${e.exploits} PoC</option>`
  ).join('');
  if (currentEval && evals.some(e => e.id === currentEval)) {
    sel.value = currentEval;
  } else if (evals.length) {
    currentEval = evals[0].id;
    window.currentEval = currentEval;
    sel.value = currentEval;
  }
}

async function refreshAll() {
  if (!currentEval) return;
  try {
    const [summary, agents, queue, findings] = await Promise.all([
      jget(`/api/evaluations/${currentEval}/summary`),
      jget(`/api/evaluations/${currentEval}/agents`),
      jget(`/api/evaluations/${currentEval}/queue?limit=80`),
      jget(`/api/evaluations/${currentEval}/findings?survived_only=${$('survivedOnly').checked}`),
    ]);
    renderMeta(summary);
    renderAgents(agents);
    renderQueue(queue);
    renderFindings(findings);
  } catch (e) { console.error(e); }
}

function renderMeta(s) {
  const ev = s.evaluation;
  const cites = s.citations || {accepted:0, rejected:0};
  $('metaStrip').textContent =
    `${ev.target_path} · ${ev.target_revision} · cites: ${cites.accepted} ok / ${cites.rejected} rejected`;
}

function renderAgents(agents) {
  $('agentCount').textContent = agents.length;
  if (!agents.length) { $('agentsBody').innerHTML = '<div class="empty">No agents registered.</div>'; return; }
  const rows = agents.map(a => {
    const stale = a.age_s != null && a.age_s > 90;
    const dot = stale ? '<span class="pill bad">stale</span>'
                      : a.state === 'running' ? '<span class="pill ok">running</span>'
                      : '<span class="pill neutral">' + escape(a.state) + '</span>';
    return `<tr>
      <td><span class="mono">${escape(a.role)}<span class="small">#${a.instance_index}</span></span></td>
      <td>${dot}</td>
      <td><span class="small">${a.active_claims}/${a.completed}</span></td>
      <td><span class="small">${ago(a.last_heartbeat)}</span></td>
    </tr>`;
  }).join('');
  $('agentsBody').innerHTML = `<table>
    <thead><tr><th>Role</th><th>State</th><th>act/done</th><th>♥</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderQueue(rows) {
  $('queueCount').textContent = rows.length;
  if (!rows.length) { $('queueBody').innerHTML = '<div class="empty">Queue empty.</div>'; return; }
  const counts = {};
  rows.forEach(r => { counts[r.state] = (counts[r.state]||0)+1; });
  const stat = Object.entries(counts).map(([k,v]) =>
    `<span class="pill ${k==='ready'?'accent':k==='claimed'?'warn':k==='done'?'ok':'bad'}">${k} ${v}</span>`
  ).join(' ');
  const body = rows.slice(0, 30).map(r => `<tr>
      <td><span class="mono small">${escape(r.task_kind)}</span></td>
      <td><span class="pill ${r.state==='ready'?'accent':r.state==='claimed'?'warn':r.state==='done'?'ok':'bad'}">${escape(r.state)}</span></td>
      <td class="small">${escape(r.claimed_by_role || '—')}</td>
    </tr>`).join('');
  $('queueBody').innerHTML = `<div class="legend">${stat}</div><table><tbody>${body}</tbody></table>`;
}

function renderFindings(rows) {
  $('findingsCount').textContent = rows.length;
  if (!rows.length) { $('findingsBody').innerHTML = '<div class="empty">No findings yet.</div>'; return; }
  const body = rows.map(f => `<tr data-id="${f.id}" class="${f.id===selectedFinding?'selected':''}">
      <td>${verdictPill(f.verdict)}</td>
      <td>${sevPill(f.severity)}</td>
      <td><span class="mono">${escape(f.vuln_class)}</span></td>
      <td><span class="mono small">${escape(f.symbol)}</span><div class="small">${escape(f.path)}</div></td>
      <td><span class="pill ${f.citations>0?'ok':'neutral'}">${f.citations}c</span>
          ${f.exploits>0?'<span class="pill bad">PoC</span>':''}
          ${f.survived_gate?'<span class="pill ok">✓</span>':''}</td>
    </tr>`).join('');
  $('findingsBody').innerHTML = `<table>
    <thead><tr><th>Verdict</th><th>Sev</th><th>Class</th><th>Symbol</th><th>Evidence</th></tr></thead>
    <tbody>${body}</tbody></table>`;
  $('findingsBody').querySelectorAll('tr[data-id]').forEach(tr => {
    tr.addEventListener('click', () => loadDetail(tr.dataset.id));
  });
}

async function loadDetail(fid) {
  selectedFinding = fid;
  $('findingsBody').querySelectorAll('tr').forEach(t => t.classList.toggle('selected', t.dataset.id===fid));
  $('detailBody').innerHTML = '<div class="empty">Loading…</div>';
  try {
    const [d, tl] = await Promise.all([
      jget(`/api/findings/${fid}`),
      jget(`/api/evaluations/${currentEval}/timeline?finding_id=${fid}&limit=80`),
    ]);
    renderDetail(d, tl);
  } catch (e) {
    $('detailBody').innerHTML = '<div class="empty">Error: ' + escape(e.message) + '</div>';
  }
}

function highlightBody(body, citations) {
  let out = escape(body || "");
  citations.forEach(c => {
    if (!c.quoted_excerpt) return;
    const needle = escape(c.quoted_excerpt);
    if (needle.length < 4) return;
    out = out.split(needle).join(`<span class="hl">${needle}</span>`);
  });
  return out;
}

function renderDetail(d, tl) {
  const f = d.finding;
  $('detailTitle').innerHTML = `Detail <span class="badge mono">${escape(f.vuln_class)}</span>`;
  const cites = (d.citations||[]).map(c => `
    <div class="citation">
      <div class="who">${escape(c.cite_path)} <span class="mono">::</span> ${escape(c.cite_symbol)} ·
        <span class="pill ok">resolved</span></div>
      <div class="ex">${escape(c.quoted_excerpt)}</div>
    </div>`).join('') || '<div class="small">No citations recorded.</div>';

  const exploits = (d.exploits||[]).map(ep => `
    <div class="citation">
      <div class="who"><span class="pill bad">PoC</span>
        author <span class="mono">${escape((ep.poc_author_agent_id||'').slice(0,8))}</span> ·
        runner <span class="mono">${escape((ep.runner_agent_id||'').slice(0,8))}</span>
        ${ep.poc_author_agent_id !== ep.runner_agent_id ? '<span class="pill ok">✓ independent</span>' : '<span class="pill bad">⚠ same agent</span>'}</div>
      <div class="ex">${escape(ep.observed_impact)}</div>
      <div class="small">artifact: <span class="mono">${escape(ep.artifact_uri)}</span></div>
    </div>`).join('') || '';

  const symPanel = d.symbol ? `
    <details open><summary>Source — ${escape(d.symbol.path)} :: ${escape(d.symbol.symbol)}
      <span class="small">L${d.symbol.start_line}–${d.symbol.end_line}</span></summary>
    <pre class="code">${highlightBody(d.symbol.body, d.citations||[])}</pre></details>` : '';

  const events = tl.map(t => `
    <div class="timeline-row">
      <span class="t">${new Date(t.timestamp).toLocaleTimeString()}</span>
      <span class="r">${escape(t.role)}</span>
      <span>${escape(t.event_type)}${t.tokens_in?` <span class="small">(${t.tokens_in}+${t.tokens_out||0}t)</span>`:''}</span>
    </div>`).join('') || '<div class="small">No events.</div>';

  $('detailBody').innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="v">${verdictPill(f.verdict)}</div><div class="l">verdict</div></div>
      <div class="stat"><div class="v">${sevPill(f.severity)}</div><div class="l">severity</div></div>
      <div class="stat"><div class="v">${f.survived_gate?'<span class="pill ok">yes</span>':'<span class="pill neutral">no</span>'}</div><div class="l">survived gate</div></div>
    </div>
    <div class="small mono" style="margin: 6px 0 10px; word-break: break-all">fp: ${escape(f.fingerprint)}</div>
    <details open><summary>Triager rationale</summary>
      <div style="padding:6px 0">${escape(f.triager_notes||f.detector_rationale||'—')}</div></details>
    <details open><summary>Evidence citations (${(d.citations||[]).length} resolved)</summary>
      ${cites}</details>
    ${exploits ? `<details open><summary>Exploit proofs</summary>${exploits}</details>` : ''}
    ${symPanel}
    <details><summary>Timeline (${tl.length} events)</summary>${events}</details>
  `;
}

$('evalSelect').addEventListener('change', e => {
  currentEval = e.target.value; window.currentEval = currentEval; selectedFinding = null;
  if (activeTab === 'pipeline') refreshAll();
  else if (activeTab === 'tracing') loadTrace();
  else if (activeTab === 'workflow' && window.vfLoadWorkflow) window.vfLoadWorkflow();
});
$('survivedOnly').addEventListener('change', refreshAll);

// ── Tab switching ────────────────────────────────────────────────────────────
let activeTab = 'pipeline';
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeTab = btn.dataset.tab;
    $('pipelineView').style.display = activeTab === 'pipeline' ? 'grid' : 'none';
    $('tracingView').style.display  = activeTab === 'tracing'  ? 'block' : 'none';
    $('workflowView').style.display = activeTab === 'workflow' ? 'block' : 'none';
    if (activeTab === 'tracing') requestAnimationFrame(() => requestAnimationFrame(loadTrace));
    if (activeTab === 'workflow') requestAnimationFrame(() => requestAnimationFrame(loadWorkflow));
  });
});

// ── Tracing / D3 graph ───────────────────────────────────────────────────────
const ROLE_COLOR = {
  indexer:        '#5dd6ff',
  cartographer:   '#7df0a8',
  detector:       '#ffb86b',
  triager:        '#c792ea',
  validator:      '#ff6f8b',
  reporter:       '#82aaff',
  coverage_guide: '#c3e88d',
};
const PIPELINE_X = { orchestrator:0, indexer:0, cartographer:1, detector:2, triager:3, validator:4, reporter:5, coverage_guide:6 };

async function loadTrace() {
  if (!currentEval) return;
  try {
    const data = await jget(`/api/evaluations/${currentEval}/trace`);
    renderTrace(data);
  } catch(e) { console.error('trace', e); }
}

function renderTrace(raw) {
  const svg = d3.select('#traceGraph');
  svg.selectAll('*').remove();

  const container = $('tracingView');
  const W = container.clientWidth  || container.offsetWidth  || 900;
  const H = container.clientHeight || container.offsetHeight || 600;
  svg.attr('viewBox', `0 0 ${W} ${H}`).attr('width', W).attr('height', H);

  // Aggregate instances → roles
  const roleMap = {};
  raw.nodes.forEach(n => {
    const r = n.role;
    if (!roleMap[r]) roleMap[r] = {id: r, role: r, instances: 0, completed: 0, events: 0, tokens: 0, stale: 0};
    roleMap[r].instances++;
    roleMap[r].completed += parseInt(n.completed) || 0;
    roleMap[r].events    += parseInt(n.events)    || 0;
    roleMap[r].tokens    += parseInt(n.tokens)    || 0;
    if (n.age_s > 90) roleMap[r].stale++;
  });
  const nodes = Object.values(roleMap);
  const numCols = Math.max(...nodes.map(n => PIPELINE_X[n.role] ?? 3)) + 1;

  // Layered layout: pipeline x, vertical lane y based on whether the role
  // is on the main pipeline (centre) vs auxiliary (above/below).
  const auxLanes = { orchestrator: -1.6, coverage_guide: -1, validator_runner: 1 };
  const xPad = 110;
  nodes.forEach(n => {
    const col = PIPELINE_X[n.role] ?? 3;
    const lane = auxLanes[n.role] ?? 0;
    n.fx = xPad + col * ((W - 2*xPad) / Math.max(numCols - 1, 1));
    n.fy = H/2 + lane * 130;
  });

  // Edges
  const edgeSet = new Map();
  raw.edges.forEach(e => {
    const key = `${e.from_role}→${e.to_role}`;
    if (!edgeSet.has(key) || edgeSet.get(key).weight < e.weight) {
      edgeSet.set(key, {source: e.from_role, target: e.to_role, weight: parseInt(e.weight)||1});
    }
  });
  const links = Array.from(edgeSet.values())
    .filter(e => nodes.some(n=>n.id===e.source) && nodes.some(n=>n.id===e.target));
  const wMax = Math.max(1, ...links.map(l => l.weight));

  const rScale = d3.scaleSqrt().domain([0, Math.max(1, ...nodes.map(n=>n.completed))]).range([28, 56]);
  nodes.forEach(n => { n.r = rScale(n.completed); });

  // Defs: per-role gradients + glow + arrow markers
  const defs = svg.append('defs');
  nodes.forEach(n => {
    const c = ROLE_COLOR[n.role] || '#5dd6ff';
    const grad = defs.append('radialGradient')
      .attr('id', `g-${n.role}`)
      .attr('cx', '35%').attr('cy', '35%').attr('r', '70%');
    grad.append('stop').attr('offset', '0%').attr('stop-color', c).attr('stop-opacity', .55);
    grad.append('stop').attr('offset', '100%').attr('stop-color', c).attr('stop-opacity', .12);
  });
  // Per-role arrow markers so the arrow tint matches the source edge
  Object.entries(ROLE_COLOR).concat([['default', '#3a4350']]).forEach(([k, c]) => {
    defs.append('marker')
      .attr('id', `arrow-${k}`)
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 9).attr('refY', 0)
      .attr('markerWidth', 7).attr('markerHeight', 7)
      .attr('orient', 'auto')
      .attr('markerUnits', 'userSpaceOnUse')
      .append('path')
        .attr('d', 'M0,-4L9,0L0,4Z')
        .attr('fill', c);
  });

  // Drop-shadow filter for nodes
  const filter = defs.append('filter')
    .attr('id', 'shadow').attr('x', '-50%').attr('y', '-50%')
    .attr('width', '200%').attr('height', '200%');
  filter.append('feGaussianBlur').attr('stdDeviation', 3).attr('result', 'b');
  filter.append('feOffset').attr('in', 'b').attr('dy', 2).attr('result', 'ob');
  filter.append('feMerge').selectAll('feMergeNode')
    .data(['ob', 'SourceGraphic']).join('feMergeNode').attr('in', d => d);

  // Force simulation: x is fixed, y is fixed too — pure layered DAG
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(140).strength(0))
    .alphaDecay(.1);

  // Edges (curved paths so we can shorten them to circle boundary)
  const linkSel = svg.append('g').attr('class', 'links')
    .selectAll('path')
    .data(links)
    .join('path')
      .attr('fill', 'none')
      .attr('stroke-linecap', 'round')
      .attr('stroke-width', d => 1.2 + 3.5 * d.weight / wMax)
      .attr('stroke', d => {
        const src = nodes.find(n => n.id === (d.source.id || d.source));
        return src ? (ROLE_COLOR[src.role] || '#3a4350') : '#3a4350';
      })
      .attr('opacity', .55)
      .attr('marker-end', d => {
        const src = nodes.find(n => n.id === (d.source.id || d.source));
        return `url(#arrow-${src ? src.role : 'default'})`;
      });

  // Edge weight chips (white-on-bg pill at midpoint)
  const edgeChip = svg.append('g')
    .selectAll('g').data(links).join('g').attr('class', 'edge-chip');
  edgeChip.append('rect')
    .attr('rx', 8).attr('ry', 8)
    .attr('fill', 'var(--panel-2, #1a1f26)')
    .attr('stroke', 'var(--border, #2a313b)');
  edgeChip.append('text')
    .attr('class', 'edge-label')
    .attr('text-anchor', 'middle').attr('dy', 4)
    .text(d => d.weight);

  // Nodes
  const node = svg.append('g').attr('class', 'nodes')
    .selectAll('g').data(nodes).join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer')
      .call(d3.drag()
        .on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(.2).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag',  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
        .on('end',   (ev, d) => { if (!ev.active) sim.alphaTarget(0); })
      )
      .on('click', (ev, d) => showNodePanel(d))
      .on('mouseenter', (ev, d) => {
        linkSel.attr('opacity', l =>
          (l.source.id||l.source) === d.id || (l.target.id||l.target) === d.id ? .95 : .15);
      })
      .on('mouseleave', () => linkSel.attr('opacity', .55));

  // Outer halo ring for visual polish
  node.append('circle')
      .attr('r', d => d.r + 6)
      .attr('fill', 'none')
      .attr('stroke', d => ROLE_COLOR[d.role] || '#5dd6ff')
      .attr('stroke-width', 1)
      .attr('stroke-opacity', .25);

  node.append('circle')
      .attr('r', d => d.r)
      .attr('fill', d => `url(#g-${d.role})`)
      .attr('stroke', d => ROLE_COLOR[d.role] || '#5dd6ff')
      .attr('stroke-width', 2.2)
      .attr('filter', 'url(#shadow)');

  // Instance count badge (top-right)
  const badge = node.append('g').attr('transform', d => `translate(${d.r * .7}, ${-d.r * .7})`);
  badge.append('circle').attr('r', 11)
      .attr('fill', '#06080a')
      .attr('stroke', d => ROLE_COLOR[d.role] || '#5dd6ff')
      .attr('stroke-width', 1.5);
  badge.append('text')
      .attr('text-anchor', 'middle').attr('dy', 4)
      .style('font', '600 11px var(--mono, monospace)')
      .style('fill', d => ROLE_COLOR[d.role] || '#5dd6ff')
      .text(d => `×${d.instances}`);

  node.append('text').attr('class', 'node-label')
      .attr('text-anchor', 'middle').attr('dy', -4)
      .style('font-weight', '600')
      .text(d => d.role.replace('_', ' '));

  node.append('text').attr('class', 'node-sub')
      .attr('text-anchor', 'middle').attr('dy', 12)
      .text(d => `${d.completed} done`);

  node.append('text').attr('class', 'node-sub')
      .attr('text-anchor', 'middle').attr('dy', 26)
      .style('fill', '#5dd6ff')
      .text(d => `${d.tokens > 1000 ? (d.tokens/1000).toFixed(1)+'k' : d.tokens}t`);

  // Geometry: shorten link to stop *outside* the target circle so the arrow
  // sits cleanly on the rim instead of being swallowed.
  function trimmedPath(d) {
    const sx = d.source.x, sy = d.source.y;
    const tx = d.target.x, ty = d.target.y;
    const dx = tx - sx, dy = ty - sy;
    const dist = Math.hypot(dx, dy) || 1;
    const ux = dx / dist, uy = dy / dist;
    const sR = (d.source.r || 30) + 2;
    const tR = (d.target.r || 30) + 6; // extra for arrowhead size
    const x1 = sx + ux * sR, y1 = sy + uy * sR;
    const x2 = tx - ux * tR, y2 = ty - uy * tR;
    // Subtle quadratic curve: offset midpoint perpendicular to the line.
    const mx = (x1 + x2) / 2 + (-uy) * 18;
    const my = (y1 + y2) / 2 + ( ux) * 18;
    return {d: `M${x1},${y1} Q${mx},${my} ${x2},${y2}`, mx, my};
  }

  sim.on('tick', () => {
    linkSel.each(function(d) {
      const p = trimmedPath(d);
      d.__mid = [p.mx, p.my];
      d3.select(this).attr('d', p.d);
    });
    edgeChip.attr('transform', d => `translate(${(d.__mid||[0,0])[0]}, ${(d.__mid||[0,0])[1]})`);
    edgeChip.select('rect')
      .attr('x', d => -10 - String(d.weight).length * 3)
      .attr('y', -9)
      .attr('width', d => 20 + String(d.weight).length * 6)
      .attr('height', 18);
    node.attr('transform', d => `translate(${d.x||0},${d.y||0})`);
  });

  // run a few sync ticks to position before paint
  for (let i = 0; i < 60; i++) sim.tick();
  sim.alpha(0);
}

async function showNodePanel(d) {
  const p = $('tracePanel');
  p.style.display = 'block';
  const isCarto = d.role === 'cartographer';
  const isReporter = d.role === 'reporter';
  const isCoverage = d.role === 'coverage_guide';
  const isIndexer = d.role === 'indexer';
  p.innerHTML = `
    <div class="panel-head">
      <h3>${escape(d.role.replace(/_/g,' '))}</h3>
      <button class="panel-close" onclick="$('tracePanel').style.display='none'" title="Close">×</button>
    </div>
    <div class="kv"><span class="k">instances</span><span class="v">${d.instances}</span></div>
    <div class="kv"><span class="k">tasks done</span><span class="v">${d.completed}</span></div>
    <div class="kv"><span class="k">log events</span><span class="v">${d.events}</span></div>
    <div class="kv"><span class="k">tokens used</span><span class="v">${d.tokens.toLocaleString()}</span></div>
    ${d.stale > 0 ? `<div style="margin-top:8px"><span class="pill warn">⚠ ${d.stale} stale</span></div>` : ''}
    ${isIndexer ? `<details open style="margin-top:10px">
      <summary>Index output</summary>
      <div id="rolePanelIndex" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    ${isCarto ? `<details open style="margin-top:10px">
      <summary>Security map documents</summary>
      <div id="rolePanelDocs" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    ${isReporter ? `<details open style="margin-top:10px">
      <summary>Report outputs</summary>
      <div id="rolePanelReports" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    ${isCoverage ? `<details open style="margin-top:10px">
      <summary>Coverage state</summary>
      <div id="rolePanelCoverage" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    <details open style="margin-top:10px">
      <summary>Tasks done <span class="pill ok mono">${d.completed}</span></summary>
      <div id="rolePanelTasks" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>
  `;
  if (isIndexer) renderIndex('rolePanelIndex');
  if (isCarto) renderDocLinks('rolePanelDocs');
  if (isReporter) renderReportLinks('rolePanelReports');
  if (isCoverage) renderCoverage('rolePanelCoverage');
  try {
    const r = await jget(`/api/evaluations/${currentEval}/role_tasks?role=${encodeURIComponent(d.role)}&limit=80`);
    renderRoleTasks(r);
  } catch(e) {
    $('rolePanelTasks').innerHTML = `<div class="small">Error: ${escape(e.message)}</div>`;
  }
}

function renderRoleTasks(r, targetId) {
  const dst = $(targetId || 'rolePanelTasks');
  if (!dst) return;
  const c = r.counts || {};
  const counters = `
    <div class="stat-row" style="margin: 4px 0 8px">
      ${(c.done   ?? 0) > 0 ? `<span class="pill ok">${c.done} done</span>`       : ''}
      ${(c.claimed?? 0) > 0 ? `<span class="pill warn">${c.claimed} active</span>` : ''}
      ${(c.ready  ?? 0) > 0 ? `<span class="pill accent">${c.ready} ready</span>`  : ''}
      ${(c.failed ?? 0) > 0 ? `<span class="pill bad">${c.failed} failed</span>`   : ''}
    </div>`;
  if (!r.tasks.length) {
    dst.innerHTML = counters + '<div class="small">No tasks recorded.</div>';
    return;
  }
  const items = r.tasks.map(t => {
    const payload = typeof t.task_payload === 'object'
      ? Object.entries(t.task_payload || {}).slice(0, 6).map(([k,v]) =>
          `<div class="kv"><span class="k">${escape(k)}</span><span class="v">${escape(typeof v==='object'?JSON.stringify(v).slice(0,40):String(v).slice(0,40))}</span></div>`
        ).join('')
      : '';
    const stateCls = t.state==='done'?'ok':t.state==='claimed'?'warn':t.state==='ready'?'accent':'bad';
    return `<details class="task-item" style="margin: 4px 0; border-left: 2px solid var(--border); padding-left: 8px">
      <summary style="color: var(--text); font-family: var(--mono); font-size: 11.5px">
        <span class="pill ${stateCls}">${escape(t.state)}</span>
        ${escape(t.task_kind)}
        ${t.attempts > 1 ? `<span class="pill warn">×${t.attempts}</span>` : ''}
      </summary>
      <div style="margin-top: 4px">
        ${payload || '<div class="small">no payload</div>'}
        <div class="kv"><span class="k">updated</span><span class="v">${ago(t.updated_at)}</span></div>
        ${t.last_error ? `<div class="small" style="color:var(--bad); margin-top:4px">⚠ ${escape(t.last_error.slice(0,200))}</div>` : ''}
      </div>
    </details>`;
  }).join('');
  dst.innerHTML = counters + items;
}

// ── Cartographer security_map docs: links + markdown modal ─────────────────────
const DOC_KINDS = ['overview','attack_surface','trust_boundaries','data_flows','threat_model'];
const DOC_TITLES = {
  overview:         'Overview',
  attack_surface:   'Attack Surface',
  trust_boundaries: 'Trust Boundaries',
  data_flows:       'Data Flows',
  threat_model:     'Threat Model',
};

async function renderDocLinks(targetId) {
  const dst = $(targetId);
  if (!dst) return;
  try {
    const r = await jget(`/api/evaluations/${currentEval}/security_map`);
    const byKind = Object.fromEntries((r.docs||[]).map(d => [d.doc_kind, d]));
    const html = DOC_KINDS.map(k => {
      const d = byKind[k];
      if (!d) {
        return `<div class="doc-link" style="color:var(--muted);cursor:default;opacity:.5">📄 ${DOC_TITLES[k]} <span class="doc-fallback">— not generated</span></div>`;
      }
      const fb = d.is_fallback ? '<span class="doc-fallback">⚠ fallback</span>' : '';
      return `<a class="doc-link" onclick="openDocModal('${k}')">📄 ${DOC_TITLES[k]} ${fb}</a>`;
    }).join('');
    dst.innerHTML = html || '<div class="small">No documents.</div>';
  } catch(e) {
    dst.innerHTML = `<div class="small">Error: ${escape(e.message)}</div>`;
  }
}

// Minimal markdown→HTML renderer (headings, lists, code, bold, italic, links, blockquote, hr, paragraphs).
function renderMarkdown(md) {
  if (!md) return '<p><em>(empty)</em></p>';
  const esc = (s) => s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  // Extract fenced code blocks first (preserve verbatim)
  const codeBlocks = [];
  md = md.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, body) => {
    codeBlocks.push(`<pre><code>${esc(body.replace(/\n$/,''))}</code></pre>`);
    return `\u0000CODE${codeBlocks.length-1}\u0000`;
  });
  let html = esc(md);
  // Headings
  html = html.replace(/^###### (.*)$/gm, '<h6>$1</h6>')
             .replace(/^##### (.*)$/gm, '<h5>$1</h5>')
             .replace(/^#### (.*)$/gm, '<h4>$1</h4>')
             .replace(/^### (.*)$/gm, '<h3>$1</h3>')
             .replace(/^## (.*)$/gm, '<h2>$1</h2>')
             .replace(/^# (.*)$/gm, '<h1>$1</h1>');
  // Horizontal rule
  html = html.replace(/^---+\s*$/gm, '<hr>');
  // Blockquotes
  html = html.replace(/^&gt; ?(.*)$/gm, '<blockquote>$1</blockquote>');
  // Lists (group consecutive list lines)
  html = html.replace(/(^(?:[-*+] .*(?:\n|$))+)/gm, (block) => {
    const items = block.trim().split(/\n/).map(l => l.replace(/^[-*+] /, '')).map(t => `<li>${t}</li>`).join('');
    return `<ul>${items}</ul>`;
  });
  html = html.replace(/(^(?:\d+\. .*(?:\n|$))+)/gm, (block) => {
    const items = block.trim().split(/\n/).map(l => l.replace(/^\d+\. /, '')).map(t => `<li>${t}</li>`).join('');
    return `<ol>${items}</ol>`;
  });
  // Inline: bold, italic, inline code, links
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>')
             .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
             .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
             .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Paragraphs: wrap stretches of text not already wrapped
  html = html.split(/\n{2,}/).map(chunk => {
    const t = chunk.trim();
    if (!t) return '';
    if (/^<(h\d|ul|ol|pre|blockquote|hr|table)/.test(t)) return t;
    return `<p>${t.replace(/\n/g,'<br>')}</p>`;
  }).join('\n');
  // Restore code blocks
  html = html.replace(/\u0000CODE(\d+)\u0000/g, (_, i) => codeBlocks[+i]);
  return html;
}

async function openDocModal(kind) {
  const m = $('docModal');
  $('docModalTitle').textContent = DOC_TITLES[kind] || kind;
  $('docModalBody').innerHTML = '<div class="small">Loading…</div>';
  $('docModalFoot').textContent = '';
  m.classList.add('active');
  try {
    const r = await jget(`/api/evaluations/${currentEval}/security_map`);
    const doc = (r.docs||[]).find(d => d.doc_kind === kind);
    if (!doc) {
      $('docModalBody').innerHTML = '<p><em>Document not found.</em></p>';
      return;
    }
    $('docModalBody').innerHTML = renderMarkdown(doc.content);
    $('docModalFoot').textContent =
      `${doc.is_fallback ? '⚠ fallback content · ' : ''}updated ${ago(doc.updated_at)} ago · ${doc.content.length} chars`;
  } catch(e) {
    $('docModalBody').innerHTML = `<p style="color:var(--bad)">Error: ${escape(e.message)}</p>`;
  }
}

// ── Reporter outputs (report.md / findings.sarif) ─────────────────────────────
async function renderReportLinks(targetId) {
  const dst = $(targetId);
  if (!dst) return;
  try {
    const r = await jget(`/api/evaluations/${currentEval}/report`);
    if (!r.files || !r.files.length) {
      dst.innerHTML = `<div class="small">No report files in <code>${escape(r.output_dir||'?')}</code>.</div>`;
      return;
    }
    const ICON = { markdown:'📝', sarif:'🧾' };
    const LBL  = { 'report.md':'Report (Markdown)', 'findings.sarif':'Findings (SARIF)' };
    const html = r.files.map(f =>
      `<a class="doc-link" onclick="openReportModal('${f.name}')">${ICON[f.kind]||'📄'} ${LBL[f.name]||f.name}
         <span class="doc-fallback">${(f.size/1024).toFixed(1)} KB</span></a>`
    ).join('');
    dst.innerHTML = html + `<div class="small" style="color:var(--muted);margin-top:6px;font-size:10.5px">📂 ${escape(r.output_dir)}</div>`;
  } catch(e) {
    dst.innerHTML = `<div class="small">Error: ${escape(e.message)}</div>`;
  }
}

async function openReportModal(filename) {
  const m = $('docModal');
  const title = filename === 'report.md' ? 'Report (Markdown)' : 'Findings (SARIF)';
  $('docModalTitle').textContent = title;
  $('docModalBody').innerHTML = '<div class="small">Loading…</div>';
  $('docModalFoot').textContent = '';
  m.classList.add('active');
  try {
    const res = await fetch(`/api/evaluations/${currentEval}/report/${filename}`);
    if (!res.ok) throw new Error(filename + ' ' + res.status);
    const text = await res.text();
    if (filename === 'report.md') {
      $('docModalBody').innerHTML = renderMarkdown(text);
    } else {
      // SARIF: pretty-print as JSON in a <pre>
      let pretty = text;
      try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch(e) {}
      const esc = (s) => s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
      $('docModalBody').innerHTML = `<pre><code>${esc(pretty)}</code></pre>`;
    }
    $('docModalFoot').textContent = `${filename} · ${(text.length/1024).toFixed(1)} KB`;
  } catch(e) {
    $('docModalBody').innerHTML = `<p style="color:var(--bad)">Error: ${escape(e.message)}</p>`;
  }
}

function closeDocModal() { $('docModal').classList.remove('active'); }
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { closeDocModal(); if (window.closeGraphModal) closeGraphModal(); }
});

// ── Coverage Guide visualization ─────────────────────────────────────────────
const COV_DIM_LABEL = {
  cwe_class:       { icon:'🛡️', label:'CWE classes',       hint:'one finding (triaged+) marks the class as exercised' },
  entry_point:     { icon:'🎯', label:'Entry points',      hint:'every indexed function in code_symbols' },
  goal:            { icon:'🏁', label:'Attack goals',      hint:'from config.goals.attack_goals' },
  trust_boundary:  { icon:'🚧', label:'Trust boundaries',  hint:'from cartographer trust_boundaries doc' },
};
const COV_STATUS_PILL = {
  credibly_attempted: 'ok',
  in_progress:        'warn',
  untouched:          'bad',
};
async function renderCoverage(targetId) {
  const el = $(targetId);
  if (!el || !currentEval) return;
  el.innerHTML = '<div class="small">Loading…</div>';
  try {
    const c = await jget(`/api/evaluations/${currentEval}/coverage`);
    const dims = Object.keys(c.by_dim || {});
    if (dims.length === 0) {
      el.innerHTML = `<div class="small" style="color:var(--muted)">No coverage rows yet · ${c.ticks||0} tick(s) recorded.</div>`;
      return;
    }
    let html = `<div class="small" style="color:var(--muted);margin-bottom:6px">${c.ticks} tick(s) · ${dims.length} dimension(s)</div>`;
    for (const dim of dims) {
      const meta = COV_DIM_LABEL[dim] || { icon:'•', label:dim, hint:'' };
      const t = c.totals[dim] || {};
      const items = c.by_dim[dim];
      html += `<details style="margin-top:8px" ${items.length<=20?'open':''}>
        <summary><strong>${meta.icon} ${meta.label}</strong>
          <span class="pill ok mono" title="credibly_attempted">${t.credibly_attempted||0}/${t.total||0}</span>
        </summary>
        <div class="small" style="color:var(--muted);margin:4px 0 6px">${meta.hint}</div>
        <div style="max-height:240px;overflow:auto;border:1px solid var(--border);border-radius:6px">
          <table class="mono" style="width:100%;font-size:11px;border-collapse:collapse">
            ${items.map(it => `<tr style="border-bottom:1px solid var(--border)">
              <td style="padding:3px 6px;word-break:break-all">${escape(it.item_id)}</td>
              <td style="padding:3px 6px;text-align:right;white-space:nowrap">
                <span class="pill ${COV_STATUS_PILL[it.status]||''}">${it.status.replace(/_/g,' ')}</span>
              </td>
            </tr>`).join('')}
          </table>
        </div>
      </details>`;
    }
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = `<div class="small" style="color:var(--bad)">Error: ${escape(e.message)}</div>`;
  }
}

window.openDocModal = openDocModal;
window.openReportModal = openReportModal;
window.closeDocModal = closeDocModal;
window.renderDocLinks = renderDocLinks;
window.renderReportLinks = renderReportLinks;
window.renderCoverage = renderCoverage;

// ── Indexer visualization ────────────────────────────────────────────────────
async function openSymbolModal(path, symbol) {
  $('docModal').classList.add('active');
  $('docModalTitle').textContent = symbol;
  $('docModalFoot').textContent = path;
  $('docModalBody').innerHTML = '<div class="small">Loading…</div>';
  try {
    const qs = new URLSearchParams({ path, symbol });
    const r = await jget(`/api/evaluations/${currentEval}/index/symbol?${qs}`);
    $('docModalFoot').textContent = `${r.path} · ${r.kind} · lines ${r.start_line}–${r.end_line}`;
    $('docModalBody').innerHTML = `<pre style="background:var(--panel2);padding:10px;border-radius:6px;overflow:auto;font-size:12px;line-height:1.45"><code>${escape(r.body)}</code></pre>`;
  } catch(e) {
    $('docModalBody').innerHTML = `<p style="color:var(--bad)">Error: ${escape(e.message)}</p>`;
  }
}

async function renderIndex(targetId) {
  const el = $(targetId);
  if (!el || !currentEval) return;
  el.innerHTML = '<div class="small">Loading…</div>';
  try {
    const ix = await jget(`/api/evaluations/${currentEval}/index`);
    const t = ix.totals || { files:0, symbols:0, edges:0 };
    const gateOk = ix.gate && ix.gate.queryable;
    let html = `<div class="kv"><span class="k">files</span><span class="v">${t.files}</span></div>
                <div class="kv"><span class="k">symbols</span><span class="v">${t.symbols}</span></div>
                <div class="kv"><span class="k">call edges</span><span class="v">${t.edges}</span></div>
                <div class="kv"><span class="k">index gate</span><span class="v">
                  <span class="pill ${gateOk?'ok':'bad'}">${gateOk?'queryable':'closed'}</span></span></div>
                <div style="margin:8px 0 4px">
                  <button class="run-btn" style="font-size:11px;padding:5px 10px"
                    onclick="openGraphModal()">🌐 Open call graph</button>
                </div>`;

    // Group symbols by file.
    const byFile = {};
    for (const s of (ix.symbols || [])) (byFile[s.path] = byFile[s.path] || []).push(s);

    html += `<details open style="margin-top:10px">
      <summary><strong>📁 Files & symbols</strong>
        <span class="pill ok mono" title="files indexed">${t.files} files</span>
        <span class="pill ok mono" title="symbols extracted">${t.symbols} symbols</span>
      </summary>
      <div style="max-height:280px;overflow:auto;border:1px solid var(--border);border-radius:6px;margin-top:6px">`;
    for (const f of (ix.files || [])) {
      const syms = byFile[f.path] || [];
      html += `<details style="border-bottom:1px solid var(--border)">
        <summary style="padding:5px 8px;cursor:pointer">
          <span class="mono" style="font-size:12px">${escape(f.path)}</span>
          <span class="pill ok mono" style="margin-left:6px">${f.symbols}</span>
          <span class="small" style="color:var(--muted);margin-left:6px">${f.functions||0} fn · ${f.methods||0} m</span>
        </summary>
        <table class="mono" style="width:100%;font-size:11px;border-collapse:collapse;background:var(--panel2)">
          ${syms.map(s => `<tr style="border-top:1px solid var(--border);cursor:pointer"
              onclick="openSymbolModal(${JSON.stringify(s.path).replace(/"/g,'&quot;')}, ${JSON.stringify(s.symbol).replace(/"/g,'&quot;')})">
            <td style="padding:3px 8px"><span class="pill ${s.kind==='method'?'warn':'ok'}" style="font-size:10px">${s.kind}</span></td>
            <td style="padding:3px 6px;word-break:break-all">${escape(s.symbol.split('.').slice(-1)[0])}</td>
            <td style="padding:3px 6px;text-align:right;color:var(--muted);white-space:nowrap">L${s.start_line}–${s.end_line}</td>
          </tr>`).join('')}
        </table>
      </details>`;
    }
    html += `</div></details>`;

    // Call graph sample.
    const edges = ix.edges || [];
    html += `<details style="margin-top:10px" ${edges.length<=20?'open':''}>
      <summary><strong>🔗 Call graph</strong> <span class="pill ok mono">${edges.length} edges</span></summary>
      <div style="max-height:240px;overflow:auto;border:1px solid var(--border);border-radius:6px;margin-top:6px">
        <table class="mono" style="width:100%;font-size:11px;border-collapse:collapse">
          ${edges.slice(0,200).map(e => `<tr style="border-bottom:1px solid var(--border)">
            <td style="padding:3px 6px;word-break:break-all">${escape(e.caller_symbol)}</td>
            <td style="padding:3px 4px;color:var(--muted);text-align:center">→</td>
            <td style="padding:3px 6px;word-break:break-all">${escape(e.callee_symbol)}</td>
          </tr>`).join('')}
          ${edges.length>200?`<tr><td colspan="3" class="small" style="padding:6px;text-align:center;color:var(--muted)">… ${edges.length-200} more edges</td></tr>`:''}
        </table>
      </div>
    </details>`;
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = `<div class="small" style="color:var(--bad)">Error: ${escape(e.message)}</div>`;
  }
}
window.renderIndex = renderIndex;
window.openSymbolModal = openSymbolModal;

// Graph modal — built by the Vue Flow module script (defined below).
async function openGraphModal() {
  if (!currentEval) return;
  $('graphModal').classList.add('active');
  $('graphModalTitle').textContent = 'Call graph · ' + currentEval.slice(0,8);
  $('graphModalFoot').textContent = 'Loading…';
  // Reset filter then build.
  const cb = $('graphInternalOnly');
  if (cb && !cb.dataset.bound) {
    cb.dataset.bound = '1';
    cb.addEventListener('change', () => window.cgBuild && window.cgBuild(cb.checked));
  }
  if (window.cgBuild) {
    await window.cgBuild(cb ? cb.checked : false);
  }
}
function closeGraphModal() {
  $('graphModal').classList.remove('active');
}
window.openGraphModal = openGraphModal;
window.closeGraphModal = closeGraphModal;

// ── Run new evaluation button ─────────────────────────────────────────────────
let lastRunEvalId = null;
async function refreshRunStatus() {
  try {
    const s = await jget('/api/run/status');
    const btn = $('runBtn'), st = $('runStatus');
    if (s.running) {
      btn.disabled = true; btn.classList.add('running'); btn.textContent = '⏳ Running…';
      const ago = s.started_at ? Math.round(Date.now()/1000 - s.started_at) : 0;
      st.className = 'run-status'; st.innerHTML = `<span class="spinner"></span>${ago}s elapsed`;
    } else {
      btn.disabled = false; btn.classList.remove('running'); btn.textContent = '▶ Run new evaluation';
      if (s.status === 'succeeded') {
        st.className = 'run-status ok'; st.textContent = '✓ last run succeeded';
        if (s.evaluation_id && s.evaluation_id !== lastRunEvalId) {
          lastRunEvalId = s.evaluation_id;
          // Auto-select the freshly created evaluation.
          await loadEvals();
          const sel = $('evalSelect');
          if ([...sel.options].some(o => o.value === s.evaluation_id)) {
            sel.value = s.evaluation_id;
            currentEval = s.evaluation_id; window.currentEval = currentEval;
            selectedFinding = null;
            await refreshAll();
          }
        }
      } else if (s.status === 'failed') {
        st.className = 'run-status bad'; st.textContent = `✗ last run failed (rc=${s.returncode})`;
      } else {
        st.className = 'run-status'; st.textContent = '';
      }
    }
  } catch(e) { /* ignore */ }
}

$('runBtn').addEventListener('click', async () => {
  if (!confirm('Start a new evaluation with the server config?\nThis will create a new evaluation_id and run all phases.')) return;
  $('runBtn').disabled = true;
  $('runStatus').className = 'run-status'; $('runStatus').innerHTML = '<span class="spinner"></span>starting…';
  try {
    const res = await fetch('/api/run', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(()=>({detail: res.statusText}));
      $('runStatus').className = 'run-status bad';
      $('runStatus').textContent = '✗ ' + (err.detail || res.statusText);
      $('runBtn').disabled = false;
      return;
    }
    await refreshRunStatus();
  } catch(e) {
    $('runStatus').className = 'run-status bad';
    $('runStatus').textContent = '✗ ' + e.message;
    $('runBtn').disabled = false;
  }
});

(async function init() {
  await loadEvals();
  await refreshAll();
  await refreshRunStatus();
  setInterval(loadEvals, 10000);
  setInterval(refreshAll, 2500);
  setInterval(refreshRunStatus, 2000);
})();

// Expose helpers for the Vue Flow module script.
window.jget = jget;
window.renderRoleTasks = renderRoleTasks;
// Bridge: vfLoadWorkflow is defined by the Vue Flow module below.
function loadWorkflow() { if (window.vfLoadWorkflow) window.vfLoadWorkflow(); }
</script>

<script type="module">
// ── Workflow tab via Vue Flow (n8n's underlying graph engine) ─────────────────
import { createApp, defineComponent, h, ref, shallowRef, markRaw, onMounted, nextTick } from 'https://esm.sh/vue@3.4.21';
import { VueFlow, Handle, Position, MarkerType, useVueFlow } from 'https://esm.sh/@vue-flow/core@1.42.1?deps=vue@3.4.21';
import { Background } from 'https://esm.sh/@vue-flow/background@1.3.2?deps=vue@3.4.21,@vue-flow/core@1.42.1';
import { MiniMap } from 'https://esm.sh/@vue-flow/minimap@1.5.0?deps=vue@3.4.21,@vue-flow/core@1.42.1';
import { Controls } from 'https://esm.sh/@vue-flow/controls@1.1.2?deps=vue@3.4.21,@vue-flow/core@1.42.1';

const ROLE_VISUAL = {
  orchestrator:     { icon:'🎯', color:'#3a42e9', label:'Orchestrator',     sub:'Lifecycle planner' },
  indexer:          { icon:'📚', color:'#7d7d87', label:'Indexer',          sub:'Code symbol index' },
  cartographer:     { icon:'🗺️', color:'#00b7bc', label:'Cartographer',     sub:'Cartograph docs' },
  detector:         { icon:'🔍', color:'#ff965a', label:'Detector',         sub:'Vulnerability scan' },
  triager:          { icon:'🩺', color:'#ffaa22', label:'Triager',          sub:'Triage & dedupe' },
  coverage_guide:   { icon:'🧭', color:'#9b6dd5', label:'Coverage Guide',   sub:'Re-explore gaps' },
  validator:        { icon:'🧪', color:'#2fb67c', label:'Validator',        sub:'Evidence gating' },
  validator_runner: { icon:'⚡', color:'#31c4ab', label:'Validator Runner', sub:'Exploit execution' },
  reporter:         { icon:'📝', color:'#8287eb', label:'Reporter',         sub:'Final report' },
};
const PX = { orchestrator:0, indexer:1, cartographer:2, detector:3, triager:4, validator:5, reporter:6, coverage_guide:3, validator_runner:5 };
const LY = { orchestrator:-1.4, coverage_guide:-1, validator_runner:1 };
const XS=260, YS=160, XP=120, YB=340;

// n8n-style custom node component
const N8nNode = defineComponent({
  name: 'N8nNode',
  props: ['data'],
  setup(props) {
    return () => {
      const d = props.data;
      const v = ROLE_VISUAL[d.role] || { icon:'⚙️', color:'#5dd6ff', label:d.role, sub:'' };
      return h('div', { class: 'n8n-node-card', style: { '--n8n-color': v.color } }, [
        h(Handle, { type:'target', position: Position.Left, style:{ background:'#6e7484' } }),
        h('div', { class:'n8n-node-icon' }, v.icon),
        h('div', { class:'n8n-node-body' }, [
          h('div', { class:'n8n-node-title' }, v.label),
          h('div', { class:'n8n-node-sub' }, v.sub),
          h('div', { class:'n8n-node-pills' }, [
            h('span', { class:'n8n-node-pill' }, `${d.completed} done`),
            d.instances > 1 ? h('span', { class:'n8n-node-pill' }, `${d.instances}×`) : null,
            d.stale > 0 ? h('span', { class:'n8n-node-pill warn' }, `⚠ stale`) : null,
          ]),
        ]),
        h(Handle, { type:'source', position: Position.Right, style:{ background:'#6e7484' } }),
      ]);
    };
  }
});

// Module-level reactive state
const wfNodes = ref([]);
const wfEdges = ref([]);
const wfReady = ref(false);
const wfFlowInstance = shallowRef(null);

async function buildGraphData() {
  if (!window.currentEval) return;
  const raw = await window.jget(`/api/evaluations/${window.currentEval}/trace`);

  const roleMap = {};
  raw.nodes.forEach(n => {
    if (!roleMap[n.role]) roleMap[n.role] = { role:n.role, instances:0, completed:0, events:0, tokens:0, stale:0 };
    roleMap[n.role].instances++;
    roleMap[n.role].completed += parseInt(n.completed)||0;
    roleMap[n.role].events    += parseInt(n.events)||0;
    roleMap[n.role].tokens    += parseInt(n.tokens)||0;
    if (n.age_s > 90) roleMap[n.role].stale++;
  });

  const nodes = Object.values(roleMap).map(r => ({
    id: r.role,
    type: 'n8n',
    position: { x: XP + (PX[r.role]??3)*XS, y: YB + (LY[r.role]??0)*YS },
    data: r,
  }));

  const seen = new Set(nodes.map(n=>n.id));
  const edges = raw.edges
    .filter(e => seen.has(e.from_role) && seen.has(e.to_role))
    .map((e,i) => ({
      id: `e${i}`,
      source: e.from_role,
      target: e.to_role,
      label: String(e.weight),
      type: 'smoothstep',
      animated: e.weight > 0,
      markerEnd: MarkerType.ArrowClosed,
      style: { stroke: '#6e7484', strokeWidth: 2 },
      labelStyle: { fill:'#8b96a4', fontFamily:'"SF Mono",monospace', fontSize:'10px' },
      labelBgStyle: { fill:'#1a1d24' },
    }));

  wfNodes.value = nodes;
  wfEdges.value = edges;

  // Re-fit once Vue Flow has rendered new nodes
  await nextTick();
  if (wfFlowInstance.value) {
    setTimeout(() => { try { wfFlowInstance.value.fitView({ padding: 0.2 }); } catch(e){} }, 50);
  }
}

// Bridge for the tab click handler
window.vfLoadWorkflow = buildGraphData;

window.showWfPanel = async function(d) {
  const p = document.getElementById('wfPanel');
  p.style.display = 'block';
  const v = ROLE_VISUAL[d.role] || { label: d.role, sub:'' };
  const isCarto = d.role === 'cartographer';
  const isReporter = d.role === 'reporter';
  const isCoverage = d.role === 'coverage_guide';
  const isIndexer = d.role === 'indexer';
  p.innerHTML = `
    <div class="panel-head">
      <h3>${v.label}</h3>
      <button class="panel-close" onclick="document.getElementById('wfPanel').style.display='none'">×</button>
    </div>
    <div class="small" style="color:var(--muted);margin-bottom:8px">${v.sub}</div>
    <div class="kv"><span class="k">instances</span><span class="v">${d.instances}</span></div>
    <div class="kv"><span class="k">tasks done</span><span class="v">${d.completed}</span></div>
    <div class="kv"><span class="k">log events</span><span class="v">${d.events}</span></div>
    <div class="kv"><span class="k">tokens used</span><span class="v">${(d.tokens||0).toLocaleString()}</span></div>
    ${(d.stale||0)>0?`<div style="margin-top:8px"><span class="pill warn">⚠ ${d.stale} stale</span></div>`:''}
    ${isIndexer ? `<details open style="margin-top:10px">
      <summary>Index output</summary>
      <div id="wfPanelIndex" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    ${isCarto ? `<details open style="margin-top:10px">
      <summary>Security map documents</summary>
      <div id="wfPanelDocs" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    ${isReporter ? `<details open style="margin-top:10px">
      <summary>Report outputs</summary>
      <div id="wfPanelReports" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    ${isCoverage ? `<details open style="margin-top:10px">
      <summary>Coverage state</summary>
      <div id="wfPanelCoverage" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>` : ''}
    <details open style="margin-top:10px">
      <summary>Tasks done <span class="pill ok mono">${d.completed}</span></summary>
      <div id="wfPanelTasks" style="margin-top:6px"><div class="small">Loading…</div></div>
    </details>`;
  if (isIndexer && window.renderIndex) window.renderIndex('wfPanelIndex');
  if (isCarto && window.renderDocLinks) window.renderDocLinks('wfPanelDocs');
  if (isReporter && window.renderReportLinks) window.renderReportLinks('wfPanelReports');
  if (isCoverage && window.renderCoverage) window.renderCoverage('wfPanelCoverage');
  try {
    const r = await window.jget(`/api/evaluations/${window.currentEval}/role_tasks?role=${encodeURIComponent(d.role)}&limit=80`);
    window.renderRoleTasks(r, 'wfPanelTasks');
  } catch(e) { document.getElementById('wfPanelTasks').innerHTML = `<div class="small">Error: ${e.message}</div>`; }
};

const App = defineComponent({
  setup() {
    const onPaneReady = (instance) => {
      wfFlowInstance.value = markRaw(instance);
      // If data is already loaded, fit now
      if (wfNodes.value.length) {
        setTimeout(() => { try { instance.fitView({ padding: 0.2 }); } catch(e){} }, 60);
      }
    };
    const onNodeClick = (ev) => { window.showWfPanel(ev.node.data); };
    return () => h(VueFlow, {
      nodes: wfNodes.value,
      edges: wfEdges.value,
      nodeTypes: { n8n: markRaw(N8nNode) },
      defaultViewport: { x: 0, y: 0, zoom: 0.7 },
      minZoom: 0.2, maxZoom: 2.5,
      fitViewOnInit: true,
      onPaneReady,
      onNodeClick,
    }, {
      default: () => [
        h(Background, { patternColor:'#2c313a', gap: 18 }),
        h(MiniMap, { pannable: true, maskColor:'rgba(20,24,29,.7)' }),
        h(Controls, {}),
      ],
    });
  }
});

createApp(App).mount('#vueflowRoot');

// ── Call-graph Vue Flow app (mounted into #graphFlowRoot, shown in modal) ──
const CGNode = defineComponent({
  name: 'CGNode',
  props: ['data'],
  setup(props) {
    return () => {
      const d = props.data;
      return h('div', { class: 'cg-node ' + (d.kind === 'external' ? 'external' : 'internal') }, [
        h(Handle, { type:'target', position: Position.Left, style:{ background:'#6e7484' } }),
        h('div', { class:'cg-kind' }, d.kind === 'external' ? 'external' : (d.symbolKind || 'function')),
        h('div', { class:'cg-name' }, d.name),
        d.path ? h('div', { class:'cg-path' }, d.path) : null,
        h(Handle, { type:'source', position: Position.Right, style:{ background:'#6e7484' } }),
      ]);
    };
  }
});

const cgNodes = ref([]);
const cgEdges = ref([]);
const cgFlowInstance = shallowRef(null);

async function buildCallGraph(internalOnly) {
  if (!window.currentEval) return;
  const ix = await window.jget(`/api/evaluations/${window.currentEval}/index`);
  const symbolFqns = new Set((ix.symbols || []).map(s => s.symbol));
  // Map short name -> full FQN to resolve indexer's bare-name callees ('search_users' -> 'myapp.__init__.search_users').
  const byShortName = {};
  for (const s of (ix.symbols || [])) {
    const short = s.symbol.split('.').slice(-1)[0];
    byShortName[short] = byShortName[short] || [];
    byShortName[short].push(s.symbol);
  }
  function resolveCallee(callee) {
    if (symbolFqns.has(callee)) return callee;            // direct FQN hit
    const cands = byShortName[callee];                    // bare name hit
    if (cands && cands.length === 1) return cands[0];
    return null;                                          // unresolved → external
  }

  const edges = (ix.edges || []).map(e => {
    const resolved = resolveCallee(e.callee_symbol);
    return {
      caller: e.caller_symbol,
      calleeRaw: e.callee_symbol,
      callee: resolved || e.callee_symbol,
      internal: !!resolved,
    };
  });
  const filtered = internalOnly ? edges.filter(e => e.internal) : edges;

  // Collect node ids actually used.
  const used = new Set();
  for (const e of filtered) { used.add('s::' + e.caller); used.add(e.internal ? ('s::' + e.callee) : ('x::' + e.callee)); }

  // Group internal nodes by file → vertical stack per file column.
  const fileOrder = (ix.files || []).map(f => f.path);
  const colX = {}; fileOrder.forEach((p, i) => colX[p] = i * 320);
  const externX = (fileOrder.length || 1) * 320 + 80;
  const yStep = 78;

  const nodes = [];
  // Internal symbol nodes
  const fileBuckets = {};
  for (const s of (ix.symbols || [])) {
    if (!used.has('s::' + s.symbol)) continue;
    (fileBuckets[s.path] = fileBuckets[s.path] || []).push(s);
  }
  for (const path of fileOrder) {
    const items = fileBuckets[path] || [];
    items.forEach((s, i) => {
      const short = s.symbol.split('.').slice(-1)[0];
      nodes.push({
        id: 's::' + s.symbol,
        type: 'cg',
        position: { x: colX[path] || 0, y: i * yStep },
        data: { name: short, path, symbolKind: s.kind, kind: 'internal' },
      });
    });
  }
  // External callee nodes
  const externals = [...used].filter(id => id.startsWith('x::')).map(id => id.slice(3));
  externals.forEach((c, i) => {
    nodes.push({
      id: 'x::' + c,
      type: 'cg',
      position: { x: externX, y: i * yStep },
      data: { name: c, path: '', kind: 'external' },
    });
  });

  const flowEdges = filtered.map((e, i) => ({
    id: `e${i}`,
    source: 's::' + e.caller,
    target: e.internal ? ('s::' + e.callee) : ('x::' + e.callee),
    type: 'smoothstep',
    animated: e.internal,
    style: { stroke: e.internal ? '#2fb67c' : '#ff965a', strokeWidth: e.internal ? 2 : 1.2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: e.internal ? '#2fb67c' : '#ff965a' },
  }));

  cgNodes.value = nodes;
  cgEdges.value = flowEdges;
  const internalCount = filtered.filter(e => e.internal).length;
  const externalCount = filtered.length - internalCount;
  const foot = document.getElementById('graphModalFoot');
  if (foot) foot.textContent =
    `${nodes.length} nodes · ${flowEdges.length} edges (${internalCount} internal, ${externalCount} external)`;

  if (cgFlowInstance.value) {
    await nextTick();
    setTimeout(() => { try { cgFlowInstance.value.fitView({ padding: 0.15 }); } catch(e){} }, 50);
  }
}
window.cgBuild = buildCallGraph;

const GraphApp = defineComponent({
  setup() {
    const onPaneReady = (instance) => {
      cgFlowInstance.value = markRaw(instance);
      if (cgNodes.value.length) {
        setTimeout(() => { try { instance.fitView({ padding: 0.15 }); } catch(e){} }, 60);
      }
    };
    return () => h(VueFlow, {
      nodes: cgNodes.value,
      edges: cgEdges.value,
      nodeTypes: { cg: markRaw(CGNode) },
      defaultViewport: { x: 0, y: 0, zoom: 0.8 },
      minZoom: 0.1, maxZoom: 2.5,
      fitViewOnInit: true,
      onPaneReady,
    }, {
      default: () => [
        h(Background, { patternColor:'#2c313a', gap: 18 }),
        h(MiniMap, { pannable: true, maskColor:'rgba(20,24,29,.7)' }),
        h(Controls, {}),
      ],
    });
  }
});
createApp(GraphApp).mount('#graphFlowRoot');
</script>
</body>
</html>
"""
