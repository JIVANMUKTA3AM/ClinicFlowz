"""
kb.py — Gestão da Base de Conhecimento por clínica.

Endpoints
---------
  GET    /api/kb/           — lista documentos (filtra por ?category=)
  POST   /api/kb/           — cria documento (gera embedding automaticamente)
  PUT    /api/kb/{id}       — actualiza (regenera embedding se texto mudar)
  DELETE /api/kb/{id}       — soft delete (active=false)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.core.database import get_clinica_id, get_supabase
from app.services import kb_service

router = APIRouter()

_CATEGORIES = Literal["empresa", "contato", "servico", "precificacao", "faq", "politica"]


# ─── Schemas ──────────────────────────────────────────────────────────────────

class KbCreate(BaseModel):
    category: _CATEGORIES
    title: str
    content: str
    metadata: dict = {}


class KbUpdate(BaseModel):
    category: _CATEGORIES | None = None
    title: str | None = None
    content: str | None = None
    metadata: dict | None = None
    active: bool | None = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/")
def list_kb(
    category: str | None = Query(None),
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> list[dict]:
    return kb_service.list_entities(db, clinica_id, category=category)


@router.post("/", status_code=201)
async def create_kb(
    body: KbCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    try:
        return await kb_service.create_entity(
            db,
            tenant_id=clinica_id,
            category=body.category,
            title=body.title,
            content=body.content,
            metadata=body.metadata,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{entity_id}")
async def update_kb(
    entity_id: str,
    body: KbUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    try:
        return await kb_service.update_entity(
            db,
            entity_id=entity_id,
            tenant_id=clinica_id,
            title=body.title,
            content=body.content,
            category=body.category,
            metadata=body.metadata,
            active=body.active,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{entity_id}", status_code=200)
def delete_kb(
    entity_id: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> None:
    kb_service.delete_entity(db, entity_id, clinica_id)
