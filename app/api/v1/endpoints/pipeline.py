# pipeline.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from uuid import UUID
from datetime import datetime, timezone
from app.core.database import get_supabase, get_clinica_id
from app.schemas.schemas import PipelineBase, PipelineUpdate, PipelineOut
from supabase import Client

router = APIRouter()

@router.get("/funil")
def funil_conversao(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    """Retorna contagem de pacientes por etapa do funil."""
    etapas = ["lead", "agendou", "compareceu", "orcamento", "tratamento_ativo", "concluido"]
    resultado = []
    for etapa in etapas:
        res = db.table("pipeline") \
            .select("id", count="exact") \
            .eq("clinica_id", clinica_id) \
            .eq("etapa", etapa) \
            .execute()
        resultado.append({"etapa": etapa, "total": res.count or 0})
    return resultado


@router.patch("/{paciente_id}/etapa", response_model=PipelineOut)
def avancar_etapa(
    paciente_id: UUID,
    body: PipelineUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    data = body.model_dump()
    data["etapa_updated_at"] = datetime.now(timezone.utc).isoformat()

    res = db.table("pipeline") \
        .update(data) \
        .eq("paciente_id", str(paciente_id)) \
        .eq("clinica_id", clinica_id) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Pipeline do paciente não encontrado")
    return res.data[0]


@router.get("/", response_model=List[PipelineOut])
def listar_pipeline(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    etapa: str = Query(None)
):
    query = db.table("pipeline") \
        .select("*, pacientes(nome, telefone, tags)") \
        .eq("clinica_id", clinica_id)
    if etapa:
        query = query.eq("etapa", etapa)
    return query.order("etapa_updated_at", desc=True).execute().data
