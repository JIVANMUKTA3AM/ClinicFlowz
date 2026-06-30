-- ============================================================
-- Migration 010 — Base de Conhecimento (wa_kb_entities)
--
-- Requer pgvector >= 0.5.0 (disponível no Supabase Cloud).
-- Usa HNSW index (não precisa de dados prévios, ideal para KBs
-- pequenas/médias de clínica — até ~10k entradas).
--
-- tenant_id → clinicas.id  (adaptado do schema "tenants" do task)
-- ============================================================

-- ─── Extensão ────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Tabela principal ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS wa_kb_entities (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid        NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
    category    text        NOT NULL
                CHECK (category IN ('empresa','contato','servico','precificacao','faq','politica')),
    title       text        NOT NULL,
    content     text        NOT NULL,
    embedding   vector(1536),          -- OpenAI text-embedding-3-small
    metadata    jsonb       NOT NULL DEFAULT '{}',
    active      boolean     NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- HNSW index — eficiente sem exigir rows prévias (ao contrário de ivfflat)
CREATE INDEX IF NOT EXISTS idx_wa_kb_embedding
    ON wa_kb_entities USING hnsw (embedding vector_cosine_ops);

-- Lookup por tenant/categoria
CREATE INDEX IF NOT EXISTS idx_wa_kb_tenant_cat
    ON wa_kb_entities (tenant_id, category) WHERE active = true;

-- ─── updated_at automático ───────────────────────────────────
DROP TRIGGER IF EXISTS trg_wa_kb_updated_at ON wa_kb_entities;
CREATE TRIGGER trg_wa_kb_updated_at
    BEFORE UPDATE ON wa_kb_entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── Função de busca semântica ───────────────────────────────
-- Chamada via db.rpc("search_kb_entries", {...}) do Python.
-- Retorna linhas ordenadas por similaridade coseno descendente.
CREATE OR REPLACE FUNCTION search_kb_entries(
    query_embedding vector(1536),
    tenant_id_input uuid,
    top_k           int DEFAULT 5
)
RETURNS TABLE (
    id          uuid,
    category    text,
    title       text,
    content     text,
    metadata    jsonb,
    similarity  float
)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
    SELECT
        id,
        category,
        title,
        content,
        metadata,
        1 - (embedding <=> query_embedding) AS similarity
    FROM wa_kb_entities
    WHERE tenant_id = tenant_id_input
      AND active    = true
      AND embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT top_k;
$$;

-- ─── RLS ─────────────────────────────────────────────────────
ALTER TABLE wa_kb_entities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clinica_isolada" ON wa_kb_entities;
CREATE POLICY "clinica_isolada" ON wa_kb_entities
    USING (tenant_id = (auth.jwt() -> 'user_metadata' ->> 'clinica_id')::uuid);
