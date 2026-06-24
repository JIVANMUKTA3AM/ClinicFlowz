from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr
from app.core.database import get_supabase, get_clinica_id
from app.schemas.schemas import MedicoCreate, MedicoOut
from supabase import Client


class MedicoUpdate(BaseModel):
    nome: Optional[str] = None
    especialidade: Optional[str] = None
    cedula: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    comissao_pct: Optional[float] = None
    horarios_disponiveis: Optional[dict] = None

router = APIRouter()

@router.post("/", response_model=MedicoOut, status_code=201)
def criar_medico(
    body: MedicoCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    data = body.model_dump()
    data["clinica_id"] = clinica_id
    data["ativo"] = True
    res = db.table("medicos").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar médico")
    return res.data[0]


@router.get("/", response_model=List[MedicoOut])
def listar_medicos(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    apenas_ativos: bool = Query(True)
):
    query = db.table("medicos").select("*").eq("clinica_id", clinica_id)
    if apenas_ativos:
        query = query.eq("ativo", True)
    return query.order("nome").execute().data


@router.patch("/{medico_id}", response_model=MedicoOut)
def atualizar_medico(
    medico_id: UUID,
    body: MedicoUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=422, detail="Nenhum campo para actualizar.")
    res = (
        db.table("medicos")
        .update(data)
        .eq("id", str(medico_id))
        .eq("clinica_id", clinica_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Médico não encontrado.")
    return res.data[0]


@router.delete("/{medico_id}", status_code=204)
def desativar_medico(
    medico_id: UUID,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    """Soft delete — marca o médico como inativo."""
    res = (
        db.table("medicos")
        .update({"ativo": False})
        .eq("id", str(medico_id))
        .eq("clinica_id", clinica_id)
        .eq("ativo", True)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Médico não encontrado ou já inativo.")


@router.get("/{medico_id}/disponibilidade")
def disponibilidade_medico(
    medico_id: UUID,
    data: str = Query(..., description="YYYY-MM-DD"),
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    """Retorna slots disponíveis do médico numa data específica."""
    medico_res = db.table("medicos").select("horarios_disponiveis").eq("id", str(medico_id)).eq("clinica_id", clinica_id).single().execute()
    if not medico_res.data:
        raise HTTPException(status_code=404, detail="Médico não encontrado")

    horarios = medico_res.data.get("horarios_disponiveis", {})

    # Dia da semana em PT
    from datetime import date as date_type
    import calendar
    d = date_type.fromisoformat(data)
    dias_pt = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    dia_semana = dias_pt[d.weekday()]
    slots_do_dia = horarios.get(dia_semana, [])

    # Filtra slots já ocupados
    ocupados_res = db.table("consultas") \
        .select("data_hora, duracao_min") \
        .eq("clinica_id", clinica_id) \
        .eq("medico_id", str(medico_id)) \
        .gte("data_hora", f"{data}T00:00:00") \
        .lte("data_hora", f"{data}T23:59:59") \
        .not_.eq("status", "cancelada") \
        .execute()

    ocupados = [c["data_hora"][11:16] for c in ocupados_res.data]
    disponiveis = [s for s in slots_do_dia if s not in ocupados]

    return {"data": data, "medico_id": str(medico_id), "slots_disponiveis": disponiveis}
