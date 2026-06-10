-- Foundry Sec — Substrate schema v1
-- Encodes constitutional invariants at the data layer.
-- See ../constitution.md and ../plan.md §2.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- Evaluations
-- ============================================================================

CREATE TABLE evaluations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    target_path     TEXT NOT NULL,
    target_revision TEXT NOT NULL,
    config          JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'created',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Agents
-- ============================================================================

CREATE TABLE agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    instance_index  INT NOT NULL,
    pid             INT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT now(),
    state           TEXT NOT NULL DEFAULT 'starting',
    UNIQUE (evaluation_id, role, instance_index)
);

CREATE INDEX idx_agents_heartbeat ON agents(last_heartbeat);

-- Heartbeat function — Principle III liveness signal.
CREATE OR REPLACE FUNCTION heartbeat(p_agent UUID) RETURNS void AS $$
BEGIN
    UPDATE agents SET last_heartbeat = now() WHERE id = p_agent;
    -- Extend any active claim by this agent.
    UPDATE work_queue
       SET claim_expires_at = now() + interval '90 seconds'
     WHERE claimed_by = p_agent AND state = 'claimed';
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Work queue — atomic claim with SKIP LOCKED (Principle IV)
-- ============================================================================

CREATE TABLE work_queue (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id     UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    task_kind         TEXT NOT NULL,    -- 'index', 'cartograph_doc', 'detect_rule', 'detect_explore', 'triage', 'validate', 'report'
    task_payload      JSONB NOT NULL,
    priority          INT NOT NULL DEFAULT 100,
    state             TEXT NOT NULL DEFAULT 'ready', -- 'ready'|'claimed'|'done'|'failed'|'blocked'
    claimed_by        UUID REFERENCES agents(id),
    claim_expires_at  TIMESTAMPTZ,
    attempts          INT NOT NULL DEFAULT 0,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_wq_ready ON work_queue(evaluation_id, priority, created_at)
    WHERE state IN ('ready', 'claimed');

-- Atomic claim: returns at most one row, or none if queue empty.
-- Reclaims expired claims (Principle III: only on stale heartbeat / TTL expiry,
-- never on wall-clock task age).
CREATE OR REPLACE FUNCTION claim_one(p_evaluation UUID, p_agent UUID, p_kinds TEXT[])
RETURNS work_queue AS $$
DECLARE
    v_row work_queue;
BEGIN
    WITH next AS (
        SELECT id FROM work_queue
         WHERE evaluation_id = p_evaluation
           AND task_kind = ANY(p_kinds)
           AND (
                state = 'ready'
                OR (state = 'claimed' AND claim_expires_at < now())
           )
         ORDER BY priority, created_at
         FOR UPDATE SKIP LOCKED
         LIMIT 1
    )
    UPDATE work_queue w SET
        state = 'claimed',
        claimed_by = p_agent,
        claim_expires_at = now() + interval '90 seconds',
        attempts = w.attempts + 1,
        updated_at = now()
    FROM next
    WHERE w.id = next.id
    RETURNING w.* INTO v_row;
    RETURN v_row;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Index store — function inventory + call graph (FR-020/FR-021)
-- ============================================================================

CREATE TABLE code_symbols (
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    symbol          TEXT NOT NULL,            -- FQN, e.g., 'myapp.auth.verify_token'
    kind            TEXT NOT NULL,            -- 'function'|'method'|'class'
    start_line      INT NOT NULL,
    end_line        INT NOT NULL,
    body            TEXT NOT NULL,
    embedding       TEXT,                     -- future: pgvector, optional
    PRIMARY KEY (evaluation_id, path, symbol)
);

CREATE INDEX idx_symbols_path ON code_symbols(evaluation_id, path);

CREATE TABLE call_edges (
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    caller_path     TEXT NOT NULL,
    caller_symbol   TEXT NOT NULL,
    callee_symbol   TEXT NOT NULL,
    PRIMARY KEY (evaluation_id, caller_path, caller_symbol, callee_symbol)
);

-- Index gate signal (FR-024).
CREATE TABLE index_gate (
    evaluation_id   UUID PRIMARY KEY REFERENCES evaluations(id) ON DELETE CASCADE,
    queryable       BOOLEAN NOT NULL DEFAULT false,
    released_at     TIMESTAMPTZ
);

-- ============================================================================
-- Security map — Cartographer outputs (§5.3)
-- Each document persisted atomically via INSERT … ON CONFLICT DO UPDATE.
-- ============================================================================

CREATE TABLE security_map (
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    doc_kind        TEXT NOT NULL,  -- 'overview'|'attack_surface'|'trust_boundaries'|'data_flows'|'threat_model'
    content         TEXT NOT NULL,
    is_fallback     BOOLEAN NOT NULL DEFAULT false,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (evaluation_id, doc_kind)
);

-- ============================================================================
-- Findings — Principle VIII: fingerprint excludes line numbers and snippet hashes
-- ============================================================================

CREATE TABLE findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    -- Stable fingerprint components (Principle VIII).
    target_revision TEXT NOT NULL,
    path            TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    vuln_class      TEXT NOT NULL,            -- CWE id, e.g., 'CWE-89'
    fingerprint     TEXT GENERATED ALWAYS AS (
                        target_revision || '|' || path || '|' || symbol || '|' || vuln_class
                    ) STORED,
    -- Lifecycle
    state           TEXT NOT NULL DEFAULT 'candidate',
                    -- 'candidate'|'triaged'|'validated'|'rejected'|'reported'
    -- Detector output
    detector_mode   TEXT NOT NULL,            -- 'rule'|'exploratory'|'dep'|'secret'
    rule_id         TEXT,
    detector_rationale TEXT,
    -- Triager output
    verdict         TEXT,                      -- 'true-positive'|'false-positive'|'needs-context'|'duplicate'
    triager_notes   TEXT,
    survived_gate   BOOLEAN NOT NULL DEFAULT false,
    -- Severity
    severity        TEXT,
    -- Validator output
    exploited       BOOLEAN NOT NULL DEFAULT false,
    -- Metadata
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evaluation_id, fingerprint)
);

CREATE INDEX idx_findings_state ON findings(evaluation_id, state);
CREATE INDEX idx_findings_verdict ON findings(evaluation_id, verdict);

-- Evidence citations — Principle I enforced at insert time.
CREATE TABLE evidence_citations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id      UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    cite_path       TEXT NOT NULL,
    cite_symbol     TEXT NOT NULL,
    quoted_excerpt  TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_citations_finding ON evidence_citations(finding_id);

-- INSERT-time citation resolver: rejects citations whose excerpt is not
-- a substring of the indexed symbol's body. Principle I.
CREATE OR REPLACE FUNCTION enforce_citation_resolves() RETURNS trigger AS $$
DECLARE
    v_body TEXT;
BEGIN
    SELECT body INTO v_body
      FROM code_symbols
     WHERE evaluation_id = NEW.evaluation_id
       AND path = NEW.cite_path
       AND symbol = NEW.cite_symbol;

    IF v_body IS NULL THEN
        RAISE EXCEPTION
          'Citation rejected: symbol %.% not in index for evaluation %',
          NEW.cite_path, NEW.cite_symbol, NEW.evaluation_id
          USING ERRCODE = 'check_violation';
    END IF;

    IF position(NEW.quoted_excerpt IN v_body) = 0 THEN
        RAISE EXCEPTION
          'Citation rejected: excerpt does not appear in body of %.%',
          NEW.cite_path, NEW.cite_symbol
          USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_citation_resolves
    BEFORE INSERT ON evidence_citations
    FOR EACH ROW EXECUTE FUNCTION enforce_citation_resolves();

-- Verdict gate: a 'true-positive' verdict requires ≥1 surviving citation.
-- Enforced when the Triager flips survived_gate to true.
CREATE OR REPLACE FUNCTION enforce_evidence_gate() RETURNS trigger AS $$
DECLARE
    v_count INT;
BEGIN
    IF NEW.survived_gate AND NEW.verdict = 'true-positive' THEN
        SELECT count(*) INTO v_count FROM evidence_citations WHERE finding_id = NEW.id;
        IF v_count = 0 THEN
            RAISE EXCEPTION
              'Evidence gate: true-positive verdict requires >= 1 citation'
              USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_evidence_gate
    BEFORE UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION enforce_evidence_gate();

-- ============================================================================
-- Exploit proofs — Principle VII: independent reproduction
-- ============================================================================

CREATE TABLE exploit_proofs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id          UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    evaluation_id       UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    poc_author_agent_id UUID NOT NULL REFERENCES agents(id),
    runner_agent_id     UUID NOT NULL REFERENCES agents(id),
    artifact_uri        TEXT NOT NULL,
    observed_impact     TEXT NOT NULL,
    sandbox_log_uri     TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Principle VII: independence enforced at the data layer.
    CONSTRAINT exploit_independent_runner CHECK (poc_author_agent_id <> runner_agent_id)
);

-- ============================================================================
-- Coverage state — multi-dimensional (Principle VI)
-- ============================================================================

CREATE TABLE coverage_dimensions (
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    dim             TEXT NOT NULL,        -- 'entry_point'|'cwe_class'|'trust_boundary'|'goal'
    item_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'untouched',
                    -- 'untouched'|'in_progress'|'credibly_attempted'
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (evaluation_id, dim, item_id)
);

-- ============================================================================
-- Budget state
-- ============================================================================

CREATE TABLE budget_state (
    evaluation_id   UUID PRIMARY KEY REFERENCES evaluations(id) ON DELETE CASCADE,
    spend_cents     BIGINT NOT NULL DEFAULT 0,
    spend_cap_cents BIGINT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    halted          BOOLEAN NOT NULL DEFAULT false,
    halt_reason     TEXT
);

-- ============================================================================
-- Operator overrides (Principle X)
-- ============================================================================

CREATE TABLE overrides (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    target_kind     TEXT NOT NULL,       -- 'verdict'|'exploited'|'coverage_complete'|'auto_stop'
    target_id       UUID,
    operator        TEXT NOT NULL,
    reason          TEXT NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Session logs (NFR-007 audit chain)
-- ============================================================================

CREATE TABLE session_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id   UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    agent_id        UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    finding_id      UUID REFERENCES findings(id) ON DELETE SET NULL,
    role            TEXT NOT NULL,
    event_type      TEXT NOT NULL,        -- 'llm_call'|'tool_call'|'state_transition'|'note'
    payload         JSONB NOT NULL,
    tokens_in       INT,
    tokens_out      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_session_logs_finding ON session_logs(finding_id);
CREATE INDEX idx_session_logs_agent ON session_logs(agent_id, created_at);
