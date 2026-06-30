"""
kb_service.py — Base de Conhecimento estruturada com busca semântica.

Busca
-----
  1. Semântica (preferida):  gera embedding via OpenAI → pgvector cosine search
  2. Keyword fallback:        ILIKE em title+content quando sem OPENAI_API_KEY
                              ou quando a entrada não tem embedding ainda

Gestão
------
  list_entities, create_entity, update_entity, delete_entity
  create/update geram embedding automaticamente se OPENAI_API_KEY configurado.

Uso pelo agente
---------------
  resultado = await search_kb(db, query, tenant_id, top_k=5)
  # devolve string formatada pronta para o modelo
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

from app.core.config import settings

logger = logging.getLogger(__name__)

_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIM   = 1536


# ─── Embedding ────────────────────────────────────────────────────────────────

async def generate_embedding(text: str) -> list[float] | None:
    """
    Calls OpenAI to generate a 1536-dim embedding.
    Returns None (triggers keyword fallback) if not configured or on error.
    """
    if not settings.OPENAI_API_KEY:
        return None
    try:
        from openai import AsyncOpenAI  # type: ignore[import]
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.embeddings.create(model=_EMBED_MODEL, input=text[:8000])
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return None


# ─── Search ───────────────────────────────────────────────────────────────────

async def search_kb(
    db: Client,
    query: str,
    tenant_id: str,
    top_k: int = 5,
) -> str:
    """
    Returns a formatted string of relevant KB chunks for injection into the agent.
    Falls back to keyword search if embeddings unavailable.
    """
    embedding = await generate_embedding(query)

    if embedding:
        rows = _vector_search(db, embedding, tenant_id, top_k)
    else:
        rows = _keyword_search(db, query, tenant_id, top_k)

    if not rows:
        return "Nenhuma informação encontrada na base de conhecimento para esta consulta."

    lines = ["=== Base de Conhecimento ==="]
    for r in rows:
        category = r.get("category", "?").upper()
        title    = r.get("title", "?")
        content  = r.get("content", "")
        score    = r.get("similarity")
        score_txt = f" (relevância: {score:.0%})" if score is not None else ""
        lines.append(f"\n[{category}] {title}{score_txt}")
        lines.append(content)

    return "\n".join(lines)


def _vector_search(db: Client, embedding: list[float], tenant_id: str, top_k: int) -> list[dict]:
    try:
        res = db.rpc(
            "search_kb_entries",
            {
                "query_embedding": embedding,
                "tenant_id_input": tenant_id,
                "top_k": top_k,
            },
        ).execute()
        return res.data or []
    except Exception as exc:
        logger.warning("Vector search failed (%s) — falling back to keyword", exc)
        return []


def _keyword_search(db: Client, query: str, tenant_id: str, top_k: int) -> list[dict]:
    """
    Simple ILIKE search on title + content.
    Used when pgvector or OpenAI is unavailable.
    """
    terms = [t for t in query.lower().split() if len(t) > 2][:4]
    seen: set[str] = set()
    results: list[dict] = []

    for term in terms:
        try:
            res = (
                db.table("wa_kb_entities")
                .select("id, category, title, content, metadata")
                .eq("tenant_id", tenant_id)
                .eq("active", True)
                .or_(f"title.ilike.%{term}%,content.ilike.%{term}%")
                .limit(top_k)
                .execute()
            )
            for row in (res.data or []):
                if row["id"] not in seen:
                    seen.add(row["id"])
                    results.append(row)
        except Exception as exc:
            logger.warning("Keyword search term '%s' failed: %s", term, exc)

        if len(results) >= top_k:
            break

    return results[:top_k]


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def list_entities(db: Client, tenant_id: str, category: str | None = None) -> list[dict]:
    q = (
        db.table("wa_kb_entities")
        .select("id, category, title, content, metadata, active, created_at, updated_at")
        .eq("tenant_id", tenant_id)
        .order("category")
        .order("title")
    )
    if category:
        q = q.eq("category", category)
    return q.execute().data or []


async def create_entity(
    db: Client,
    tenant_id: str,
    category: str,
    title: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    embedding = await generate_embedding(f"{title}\n{content}")
    row: dict = {
        "tenant_id": tenant_id,
        "category":  category,
        "title":     title,
        "content":   content,
        "metadata":  metadata or {},
        "active":    True,
    }
    if embedding:
        row["embedding"] = embedding

    res = db.table("wa_kb_entities").insert(row).execute()
    if not res.data:
        raise RuntimeError("Erro ao criar entrada na KB")
    return _strip_embedding(res.data[0])


async def update_entity(
    db: Client,
    entity_id: str,
    tenant_id: str,
    *,
    title: str | None = None,
    content: str | None = None,
    category: str | None = None,
    metadata: dict | None = None,
    active: bool | None = None,
) -> dict:
    updates: dict = {}
    if title    is not None: updates["title"]    = title
    if content  is not None: updates["content"]  = content
    if category is not None: updates["category"] = category
    if metadata is not None: updates["metadata"] = metadata
    if active   is not None: updates["active"]   = active

    # Regenerate embedding if text changed
    if title is not None or content is not None:
        cur = (
            db.table("wa_kb_entities")
            .select("title, content")
            .eq("id", entity_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if cur.data:
            cur_row = cur.data[0]
            new_title   = title   or cur_row["title"]
            new_content = content or cur_row["content"]
            embedding = await generate_embedding(f"{new_title}\n{new_content}")
            if embedding:
                updates["embedding"] = embedding

    res = (
        db.table("wa_kb_entities")
        .update(updates)
        .eq("id", entity_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not res.data:
        raise RuntimeError("Entrada não encontrada ou sem permissão")
    return _strip_embedding(res.data[0])


def delete_entity(db: Client, entity_id: str, tenant_id: str) -> None:
    """Soft delete — sets active=False."""
    db.table("wa_kb_entities").update({"active": False}).eq(
        "id", entity_id
    ).eq("tenant_id", tenant_id).execute()


def _strip_embedding(row: dict) -> dict:
    """Never return raw embedding vectors to the API consumer."""
    row.pop("embedding", None)
    return row
