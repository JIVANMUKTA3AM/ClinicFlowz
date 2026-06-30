-- ============================================================
-- Migration 009 — wa_audit_log
--
-- Regista eventos de auditoria do agente WhatsApp.
-- Primeiro uso: gate G3 (book_appointment sem verificar slots).
-- Extensível para outros event_types no futuro.
--
-- Sem FK em conversation_id — logs sobrevivem ao delete da conversa.
-- Idempotente: CREATE TABLE IF NOT EXISTS.
-- ============================================================

CREATE TABLE IF NOT EXISTS wa_audit_log (
    id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    clinica_id      uuid        REFERENCES clinicas(id) ON DELETE SET NULL,
    conversation_id uuid,           -- wa_conversations.id (sem FK — logs persistem)
    event_type      text        NOT NULL,  -- g3_gate_triggered | ...
    payload         jsonb       NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wa_audit_clinica
    ON wa_audit_log (clinica_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wa_audit_event
    ON wa_audit_log (event_type, created_at DESC);

-- ─── RLS ─────────────────────────────────────────────────────
-- Clínicas vêem apenas os seus próprios logs.
-- O backend usa service_key (bypassa RLS) — correcto para jobs assíncronos.
ALTER TABLE wa_audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clinica_isolada" ON wa_audit_log;
CREATE POLICY "clinica_isolada" ON wa_audit_log
    USING (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
