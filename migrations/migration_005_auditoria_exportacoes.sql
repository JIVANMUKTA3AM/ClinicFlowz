-- ============================================================
-- migration_005_auditoria_exportacoes.sql
-- Registo de exportações de dados pessoais
-- (direito de portabilidade — LGPD / RGPD)
--
-- Cada exportação fica auditada: quem pediu, o quê, quando.
-- Segue o padrão das restantes 9 tabelas:
--   • clinica_id em todas as linhas (multi-tenant)
--   • RLS com policy "clinica_isolada"
--   • uuid pk + created_at
-- ============================================================

CREATE TABLE exportacoes_auditoria (
  id           uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  clinica_id   uuid        NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
  user_id      text        NOT NULL,   -- JWT sub (quem pediu a exportação)
  user_email   text,                   -- cópia do email para log legível
  tipo         text        NOT NULL    -- 'paciente' | 'clinica'
               CHECK (tipo IN ('paciente', 'clinica')),
  paciente_id  uuid        REFERENCES pacientes(id) ON DELETE SET NULL,
               -- NULL nas exportações de clínica; preenchido nas de paciente
  exportado_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_export_audit_clinica   ON exportacoes_auditoria(clinica_id);
CREATE INDEX idx_export_audit_paciente  ON exportacoes_auditoria(paciente_id);
CREATE INDEX idx_export_audit_user      ON exportacoes_auditoria(user_id);
CREATE INDEX idx_export_audit_exportado ON exportacoes_auditoria(exportado_at DESC);

-- ─── RLS ─────────────────────────────────────────────────────────────────────
-- Clínicas só vêem os seus próprios registos de auditoria.
-- (O backend usa service_key nos exports, que bypassa RLS — correcto
--  porque o registo de auditoria é gravado pelo próprio backend antes
--  de devolver a resposta ao utilizador.)

ALTER TABLE exportacoes_auditoria ENABLE ROW LEVEL SECURITY;

CREATE POLICY "clinica_isolada" ON exportacoes_auditoria
  USING (clinica_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);

-- ─── FIM ─────────────────────────────────────────────────────────────────────
-- Verificar com:
--   \d exportacoes_auditoria
--   SELECT COUNT(*) FROM exportacoes_auditoria;  -- deve ser 0
-- ============================================================
