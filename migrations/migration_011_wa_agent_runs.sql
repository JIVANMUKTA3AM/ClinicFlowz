-- ============================================================
-- Migration 011 — wa_agent_runs
--
-- Regista cada execução do agente (produção e sandbox).
-- source = 'production' | 'sandbox'
--
-- Não tem FK em conversation_id para sobreviver a deletes.
-- Idempotente: CREATE TABLE IF NOT EXISTS.
-- ============================================================

CREATE TABLE IF NOT EXISTS wa_agent_runs (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    clinica_id      uuid        REFERENCES clinicas(id) ON DELETE SET NULL,
    conversation_id uuid,                   -- wa_conversations.id (sem FK)
    source          text        NOT NULL DEFAULT 'production'
                    CHECK (source IN ('production', 'sandbox')),
    agent_model     text,
    input_tokens    integer     NOT NULL DEFAULT 0,
    output_tokens   integer     NOT NULL DEFAULT 0,
    cost_usd        numeric(10, 6) NOT NULL DEFAULT 0,
    latency_ms      integer,
    tools_called    jsonb       NOT NULL DEFAULT '[]',
    stage_before    text,
    stage_after     text,
    metadata        jsonb       NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wa_runs_clinica
    ON wa_agent_runs (clinica_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wa_runs_source
    ON wa_agent_runs (source, created_at DESC);

-- ─── RLS ─────────────────────────────────────────────────────
ALTER TABLE wa_agent_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clinica_isolada" ON wa_agent_runs;
CREATE POLICY "clinica_isolada" ON wa_agent_runs
    USING (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
