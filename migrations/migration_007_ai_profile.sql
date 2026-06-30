-- ============================================================
-- Migration 007 — ai_profile em pacientes
--
-- Adiciona coluna ai_profile JSONB à tabela pacientes.
-- Persiste entre conversas — dados acumulados sobre o contacto.
-- Actualizado pelo profile_updater (Claude Haiku) no encerramento
-- de cada conversa WhatsApp.
--
-- Schema do documento:
-- {
--   "preferences": {
--     "preferred_procedures": ["botox", "limpeza de pele"],
--     "preferred_days": ["segunda", "quarta"],
--     "preferred_time": "manhã|tarde|indiferente"
--   },
--   "history_summary": "Paciente com 2 consultas. Interessa-se por harmonização.",
--   "last_objection": "achou caro em maio/2026",
--   "communication_style": "formal|casual|emoji_heavy",
--   "total_consultations": 2,
--   "last_seen": "2026-06-24T10:00:00+00:00"
-- }
--
-- Idempotente: ADD COLUMN IF NOT EXISTS.
-- ============================================================

ALTER TABLE pacientes
    ADD COLUMN IF NOT EXISTS ai_profile JSONB DEFAULT '{}';

-- GIN index para queries futuras por campos do perfil
-- (ex: encontrar todos os pacientes interessados em botox)
CREATE INDEX IF NOT EXISTS idx_pacientes_ai_profile
    ON pacientes USING gin(ai_profile);

-- Sem nova política RLS necessária — pacientes já tem "clinica_isolada"
-- que protege todas as colunas da tabela.
