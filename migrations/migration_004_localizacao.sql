-- ============================================================
-- migration_004_localizacao.sql
-- CRM Clínicas — Suporte multi-país (PT / BR)
--
-- Pré-condições verificadas:
--   • Banco vazio em produção — nenhuma linha existente quebra
--     o ADD COLUMN NOT NULL sem DEFAULT.
--   • Todas as 8 policies RLS referenciam apenas clinica_id;
--     nenhuma referencia nif ou consentimento_rgpd_at.
--     Logo: zero DROP/CREATE de policies necessário.
--
-- Tabelas alteradas: clinicas, pacientes
-- Policies alteradas: nenhuma
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- 1. PAÍS DA CLÍNICA
--    Sem DEFAULT: é obrigatório e definido no onboarding.
--    Banco vazio → NOT NULL sem default é seguro.
-- ─────────────────────────────────────────────────────────────
ALTER TABLE clinicas
  ADD COLUMN pais TEXT NOT NULL
    CHECK (pais IN ('PT', 'BR'));


-- ─────────────────────────────────────────────────────────────
-- 2. IDENTIFICADOR FISCAL GENÉRICO
--    nif → documento_fiscal (ambas as tabelas)
--    A label exibida ("NIF" ou "CPF") passa a vir do código,
--    lendo clinica.pais. O banco guarda só o valor.
-- ─────────────────────────────────────────────────────────────
ALTER TABLE pacientes
  RENAME COLUMN nif TO documento_fiscal;

ALTER TABLE clinicas
  RENAME COLUMN nif TO documento_fiscal;


-- ─────────────────────────────────────────────────────────────
-- 3. CONSENTIMENTO DE PRIVACIDADE (RGPD → neutral)
--    Renomear agora enquanto o banco está vazio.
--    A lei exibida ("RGPD" para PT, "LGPD" para BR) vem do código.
--    O índice não existia na coluna original — nada a recriar.
-- ─────────────────────────────────────────────────────────────
ALTER TABLE pacientes
  RENAME COLUMN consentimento_rgpd_at TO consentimento_privacidade_at;


-- ─────────────────────────────────────────────────────────────
-- 4. ANÁLISE DAS POLICIES RLS — CONFIRMAÇÃO
--
--    Migration 001 (schema_inicial): 6 policies
--      • pacientes       "clinica_isolada" → clinica_id only ✓
--      • consultas       "clinica_isolada" → clinica_id only ✓
--      • medicos         "clinica_isolada" → clinica_id only ✓
--      • salas           "clinica_isolada" → clinica_id only ✓
--      • pipeline        "clinica_isolada" → clinica_id only ✓
--      • interacoes      "clinica_isolada" → clinica_id only ✓
--
--    Migration 002 (whatsapp_connections): 1 policy
--      • whatsapp_connections "clinica_isolada" → clinica_id only ✓
--
--    Migration 003 (scheduled_jobs): 1 policy
--      • scheduled_jobs  "clinica_isolada" → clinica_id only ✓
--
--    TOTAL: 8 policies — NENHUMA referencia nif ou
--    consentimento_rgpd_at. Não é necessário DROP/CREATE.
-- ─────────────────────────────────────────────────────────────
-- (sem DDL de policies aqui — nenhuma alteração necessária)


-- ─────────────────────────────────────────────────────────────
-- FIM — verificar com:
--   \d clinicas   → deve ter: pais text, documento_fiscal text
--   \d pacientes  → deve ter: documento_fiscal text,
--                             consentimento_privacidade_at timestamptz
-- ─────────────────────────────────────────────────────────────
