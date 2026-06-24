from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from uuid import UUID

from app.core.database import get_supabase, get_clinica_id
from app.schemas.schemas import SalaCreate, SalaUpdate, SalaOut
from supabase import Client

router = APIRouter()


@router.post("/", response_model=SalaOut, status_code=201)
def criar_sala(
    body: SalaCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    data = body.model_dump()
    data["clinica_id"] = clinica_id
    data["ativa"] = True

    res = db.table("salas").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar sala.")
    return res.data[0]


@router.get("/", response_model=List[SalaOut])
def listar_salas(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    apenas_ativas: bool = Query(True),
):
    query = db.table("salas").select("*").eq("clinica_id", clinica_id)
    if apenas_ativas:
        query = query.eq("ativa", True)
    return query.order("nome").execute().data


@router.put("/{sala_id}", response_model=SalaOut)
def atualizar_sala(
    sala_id: UUID,
    body: SalaUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=422, detail="Nenhum campo para actualizar.")

    res = (
        db.table("salas")
        .update(data)
        .eq("id", str(sala_id))
        .eq("clinica_id", clinica_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Sala não encontrada.")
    return res.data[0]


@router.delete("/{sala_id}", status_code=204)
def desativar_sala(
    sala_id: UUID,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    """Soft delete — marca a sala como inativa para preservar histórico de consultas."""
    res = (
        db.table("salas")
        .update({"ativa": False})
        .eq("id", str(sala_id))
        .eq("clinica_id", clinica_id)
        .eq("ativa", True)       # idempotente: não falha se já estiver inativa
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Sala não encontrada ou já inativa.")
