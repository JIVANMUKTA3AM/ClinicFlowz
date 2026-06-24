from fastapi import APIRouter, Depends, Query
from typing import List
from uuid import UUID
from app.core.database import get_supabase, get_clinica_id
from app.schemas.schemas import InteracaoCreate, InteracaoOut
from app.services.timeline_service import registrar_interacao
from supabase import Client

router = APIRouter()

@router.get("/{paciente_id}", response_model=List[InteracaoOut])
def timeline_paciente(
    paciente_id: UUID,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    limit: int = Query(100, le=500)
):
    """Retorna todas as interações do paciente em ordem cronológica."""
    res = db.table("interacoes") \
        .select("*") \
        .eq("paciente_id", str(paciente_id)) \
        .eq("clinica_id", clinica_id) \
        .order("created_at", desc=True) \
        .limit(limit) \
        .execute()
    return res.data


@router.post("/", response_model=InteracaoOut, status_code=201)
def criar_interacao_manual(
    body: InteracaoCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    """Recepção adiciona nota ou registo manual na timeline."""
    data = body.model_dump()
    data["clinica_id"] = clinica_id
    data["paciente_id"] = str(data["paciente_id"])
    data["criado_por"] = "recepcao"
    return registrar_interacao(db, data)
