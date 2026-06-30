-- ============================================================
-- Migration 006 — wa_conversations + context_snapshot
--
-- Cria a tabela wa_conversations (uma linha por paciente/clínica)
-- e adiciona a coluna context_snapshot JSONB para persistir o
-- estado da conversa entre turnos do agente.
--
-- Idempotente: usa IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.
-- ============================================================

-- ─── Tabela principal ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS wa_conversations (
    id               uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    clinica_id       uuid        NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
    paciente_id      uuid        NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    telefone         text        NOT NULL,
    context_snapshot jsonb       NOT NULL DEFAULT '{}',
    updated_at       timestamptz NOT NULL DEFAULT now(),

    -- Uma conversa activa por número por clínica
    CONSTRAINT uq_wa_conv_clinica_phone UNIQUE (clinica_id, telefone)
);

-- Garante que a coluna existe mesmo que a tabela já existisse sem ela
ALTER TABLE wa_conversations
    ADD COLUMN IF NOT EXISTS context_snapshot JSONB DEFAULT '{}';

-- ─── Índices ─────────────────────────────────────────────────
-- Lookup principal: clinica_id + telefone (vindo do webhook)
CREATE INDEX IF NOT EXISTS idx_wa_conv_lookup
    ON wa_conversations (clinica_id, telefone);

-- ─── updated_at automático ───────────────────────────────────
-- Reutiliza a função update_updated_at() criada em migration 001.
DROP TRIGGER IF EXISTS trg_wa_conv_updated_at ON wa_conversations;
CREATE TRIGGER trg_wa_conv_updated_at
    BEFORE UPDATE ON wa_conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── RLS ─────────────────────────────────────────────────────
-- context_snapshot só acessível pelo tenant_id da conversa.
-- O backend usa service_key (bypassa RLS) para webhooks; isto
-- protege o acesso directo via JWT de utilizadores do frontend.
ALTER TABLE wa_conversations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clinica_isolada" ON wa_conversations;
CREATE POLICY "clinica_isolada" ON wa_conversations
    USING (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
