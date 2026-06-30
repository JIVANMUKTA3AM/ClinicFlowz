-- ============================================================
-- Migration 013 — wa_agent_versions
--
-- Versioning do agente WhatsApp com gate de publicação.
-- Cada versão é um snapshot imutável da configuração completa.
-- status: 'staging' (rascunho) | 'production' (publicada/restaurada)
--
-- Idempotente: CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS.
-- ============================================================

CREATE TABLE IF NOT EXISTS wa_agent_versions (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid        NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
    agent_id         uuid        NOT NULL REFERENCES wa_agents(id) ON DELETE CASCADE,
    version_number   integer     NOT NULL,
    label            text,                   -- "v3 — mais consultiva"
    snapshot         jsonb       NOT NULL,   -- cópia: nome, playbook, model, kb_count, ...
    readiness_score  integer,               -- 0-100
    readiness_issues text[]      NOT NULL DEFAULT '{}',
    status           text        NOT NULL DEFAULT 'staging'
                     CHECK (status IN ('staging', 'production')),
    published_at     timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),

    -- Um número de versão único por agente
    CONSTRAINT uq_agent_version UNIQUE (agent_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_wa_ver_agent
    ON wa_agent_versions (agent_id, version_number DESC);

CREATE INDEX IF NOT EXISTS idx_wa_ver_tenant
    ON wa_agent_versions (tenant_id, created_at DESC);

-- Aponta para a versão actualmente em produção
ALTER TABLE wa_agents
    ADD COLUMN IF NOT EXISTS
    published_version_id uuid REFERENCES wa_agent_versions(id) ON DELETE SET NULL;

-- ─── RLS ─────────────────────────────────────────────────────
ALTER TABLE wa_agent_versions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clinica_isolada" ON wa_agent_versions;
CREATE POLICY "clinica_isolada" ON wa_agent_versions
    USING (tenant_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
