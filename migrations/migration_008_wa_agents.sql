-- ============================================================
-- Migration 008 — wa_agents + agent_playbook
--
-- Cria a tabela wa_agents (uma row por clínica — configuração
-- do agente WhatsApp) e a coluna agent_playbook JSONB.
--
-- O playbook define stages, goals, probing_questions,
-- blocked_tools e estratégias de objeção.  É carregado a cada
-- turno e injectado no system prompt do agente.
--
-- Idempotente: CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS.
-- ============================================================

CREATE TABLE IF NOT EXISTS wa_agents (
    id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    clinica_id      uuid        NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
    nome            text        NOT NULL DEFAULT 'Agente WhatsApp',
    ativo           boolean     NOT NULL DEFAULT true,
    agent_playbook  jsonb       NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_wa_agent_clinica UNIQUE (clinica_id)
);

ALTER TABLE wa_agents
    ADD COLUMN IF NOT EXISTS agent_playbook JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_wa_agents_clinica
    ON wa_agents (clinica_id) WHERE ativo = true;

DROP TRIGGER IF EXISTS trg_wa_agents_updated_at ON wa_agents;
CREATE TRIGGER trg_wa_agents_updated_at
    BEFORE UPDATE ON wa_agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── Playbook padrão ─────────────────────────────────────────
-- Inserido para cada clínica existente via INSERT ... ON CONFLICT.
-- Novas clínicas recebem o default ao primeiro GET /api/agents/.

-- ─── RLS ─────────────────────────────────────────────────────
ALTER TABLE wa_agents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clinica_isolada" ON wa_agents;
CREATE POLICY "clinica_isolada" ON wa_agents
    USING (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
