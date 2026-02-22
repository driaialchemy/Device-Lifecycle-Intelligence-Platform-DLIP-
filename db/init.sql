-- db/init.sql

-- 1) Core entities

CREATE TABLE IF NOT EXISTS devices (
  device_id               TEXT PRIMARY KEY,
  brand                   TEXT NOT NULL,
  model                   TEXT NOT NULL,
  intake_date             TIMESTAMPTZ,
  refurb_status           TEXT DEFAULT 'intake',
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
  run_id                  UUID PRIMARY KEY,
  device_id               TEXT NOT NULL REFERENCES devices(device_id),
  status                  TEXT NOT NULL DEFAULT 'started',  -- started|completed|failed
  started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at                TIMESTAMPTZ,

  -- Metadata (data about the run)
  app_version             TEXT,
  docker_image_tag        TEXT,
  git_commit              TEXT,
  llm_provider            TEXT,
  llm_model               TEXT,

  overall_decision        TEXT,   -- pass|repair|scrap
  overall_confidence      DOUBLE PRECISION,
  overall_summary         TEXT
);

-- 2) Agent outputs (append-only)

CREATE TABLE IF NOT EXISTS agent_outputs (
  output_id               UUID PRIMARY KEY,
  run_id                  UUID NOT NULL REFERENCES runs(run_id),

  agent_name              TEXT NOT NULL,   -- r2v3|gdpr|sensor|arbiter|meta
  agent_round             INTEGER NOT NULL DEFAULT 1,

  verdict                 TEXT,            -- pass|fail|needs_more_evidence
  uncertainty_score       DOUBLE PRECISION,

  summary_text            TEXT,            -- human-readable
  claims_json             JSONB,           -- machine-readable structured data
  evidence_refs_json      JSONB,           -- pointers/hashes/refs

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3) Tool events (append-only evidence that computations actually ran)

CREATE TABLE IF NOT EXISTS tool_events (
  event_id                UUID PRIMARY KEY,
  run_id                  UUID NOT NULL REFERENCES runs(run_id),

  tool_name               TEXT NOT NULL,
  tool_version            TEXT,
  status                  TEXT NOT NULL DEFAULT 'success', -- success|error

  input_hash              TEXT,
  output_hash             TEXT,
  artifact_ref            TEXT,            -- file path / object key / etc.

  execution_time_ms       INTEGER,
  metrics_json            JSONB,
  warnings_json           JSONB,

  summary_text            TEXT,            -- human-readable
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4) Tamper-evident audit chain (append-only)

CREATE TABLE IF NOT EXISTS audit_chain (
  chain_id                UUID PRIMARY KEY,
  run_id                  UUID NOT NULL REFERENCES runs(run_id),

  prev_hash               TEXT,
  current_hash            TEXT NOT NULL,
  hash_algorithm          TEXT NOT NULL DEFAULT 'sha256',
  canonical_payload_json  JSONB,

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Helpful indexes for common queries
CREATE INDEX IF NOT EXISTS idx_runs_device_id ON runs(device_id);
CREATE INDEX IF NOT EXISTS idx_agent_outputs_run_id ON agent_outputs(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_events_run_id ON tool_events(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_chain_run_id ON audit_chain(run_id);

-- Optional: a simple view for human-friendly “latest agent output per agent”
-- (Engineers can refine later; this is enough for first UI integration.)
CREATE OR REPLACE VIEW v_latest_agent_outputs AS
SELECT DISTINCT ON (run_id, agent_name)
  run_id, agent_name, agent_round, verdict, uncertainty_score, summary_text, created_at
FROM agent_outputs
ORDER BY run_id, agent_name, created_at DESC;
