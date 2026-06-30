-- ============================================================
-- Migration 012 — Colunas de saúde em wa_agent_runs + View
--
-- Adiciona 4 colunas booleanas de qualidade ao wa_agent_runs
-- (criada na migration 011) e cria a view wa_agent_health_7d.
--
-- Idempotente: ADD COLUMN IF NOT EXISTS + CREATE OR REPLACE VIEW.
-- ============================================================

-- ─── Colunas de qualidade ────────────────────────────────────
ALTER TABLE wa_agent_runs
    ADD COLUMN IF NOT EXISTS kb_miss            boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS hallucination_flag boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS handover_triggered boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS pii_blocked        boolean NOT NULL DEFAULT false;

-- Índice parcial para alertas de qualidade
CREATE INDEX IF NOT EXISTS idx_wa_runs_quality
    ON wa_agent_runs (clinica_id, created_at DESC)
    WHERE hallucination_flag = true OR kb_miss = true OR pii_blocked = true;

-- ─── View wa_agent_health_7d ─────────────────────────────────
-- Agregações dos últimos 7 dias por clínica.
-- Acedida via service_key no backend (bypass RLS).
-- Filtra source='production' para não incluir runs de sandbox.
CREATE OR REPLACE VIEW wa_agent_health_7d AS
SELECT
    clinica_id,
    COUNT(*)                                                          AS total_runs,
    COALESCE(SUM(cost_usd), 0)                                       AS total_cost_usd,
    COALESCE(AVG(cost_usd), 0)                                       AS avg_cost_usd,
    COALESCE(AVG(latency_ms), 0)                                     AS avg_latency_ms,
    COALESCE(
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0
    )                                                                 AS p95_latency_ms,
    COALESCE(SUM(input_tokens), 0)                                   AS total_input_tokens,
    COALESCE(SUM(output_tokens), 0)                                  AS total_output_tokens,
    ROUND(
        AVG(CASE WHEN kb_miss            THEN 1.0 ELSE 0 END) * 100, 1
    )                                                                 AS kb_miss_rate,
    ROUND(
        AVG(CASE WHEN hallucination_flag THEN 1.0 ELSE 0 END) * 100, 1
    )                                                                 AS hallucination_rate,
    ROUND(
        AVG(CASE WHEN handover_triggered THEN 1.0 ELSE 0 END) * 100, 1
    )                                                                 AS handover_rate,
    ROUND(
        AVG(CASE WHEN pii_blocked        THEN 1.0 ELSE 0 END) * 100, 1
    )                                                                 AS pii_rate
FROM wa_agent_runs
WHERE created_at  > now() - INTERVAL '7 days'
  AND source      = 'production'
GROUP BY clinica_id;

-- ─── View wa_agent_health_30d ────────────────────────────────
CREATE OR REPLACE VIEW wa_agent_health_30d AS
SELECT
    clinica_id,
    COUNT(*)                                                          AS total_runs,
    COALESCE(SUM(cost_usd), 0)                                       AS total_cost_usd,
    COALESCE(AVG(cost_usd), 0)                                       AS avg_cost_usd,
    COALESCE(AVG(latency_ms), 0)                                     AS avg_latency_ms,
    COALESCE(
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0
    )                                                                 AS p95_latency_ms,
    COALESCE(SUM(input_tokens), 0)                                   AS total_input_tokens,
    COALESCE(SUM(output_tokens), 0)                                  AS total_output_tokens,
    ROUND(AVG(CASE WHEN kb_miss            THEN 1.0 ELSE 0 END) * 100, 1) AS kb_miss_rate,
    ROUND(AVG(CASE WHEN hallucination_flag THEN 1.0 ELSE 0 END) * 100, 1) AS hallucination_rate,
    ROUND(AVG(CASE WHEN handover_triggered THEN 1.0 ELSE 0 END) * 100, 1) AS handover_rate,
    ROUND(AVG(CASE WHEN pii_blocked        THEN 1.0 ELSE 0 END) * 100, 1) AS pii_rate
FROM wa_agent_runs
WHERE created_at  > now() - INTERVAL '30 days'
  AND source      = 'production'
GROUP BY clinica_id;
