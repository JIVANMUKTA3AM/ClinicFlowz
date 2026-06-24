from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date, timezone
from app.core.database import get_supabase, get_clinica_id
from app.schemas.schemas import ConsultaCreate, ConsultaUpdate, ConsultaOut
from app.services.timeline_service import registrar_interacao
from supabase import Client

router = APIRouter()

@router.post("/", response_model=ConsultaOut, status_code=201)
def criar_consulta(
    body: ConsultaCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    data = body.model_dump()
    data["clinica_id"] = clinica_id
    data["data_hora"] = data["data_hora"].isoformat()
    data["paciente_id"] = str(data["paciente_id"])
    data["medico_id"] = str(data["medico_id"])
    if data.get("sala_id"):
        data["sala_id"] = str(data["sala_id"])

    # Rejeita referências cross-tenant: paciente, médico e sala devem pertencer a esta clínica
    if not db.table("pacientes").select("id").eq("id", data["paciente_id"]).eq("clinica_id", clinica_id).execute().data:
        raise HTTPException(status_code=422, detail="paciente não pertence a esta clínica")
    if not db.table("medicos").select("id").eq("id", data["medico_id"]).eq("clinica_id", clinica_id).execute().data:
        raise HTTPException(status_code=422, detail="médico não pertence a esta clínica")
    if data.get("sala_id"):
        if not db.table("salas").select("id").eq("id", data["sala_id"]).eq("clinica_id", clinica_id).execute().data:
            raise HTTPException(status_code=422, detail="sala não pertence a esta clínica")

    res = db.table("consultas").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar consulta")

    consulta = res.data[0]

    # Registra na timeline do paciente
    registrar_interacao(db, {
        "clinica_id": clinica_id,
        "paciente_id": str(body.paciente_id),
        "tipo": "consulta",
        "conteudo": f"Consulta agendada para {body.data_hora.strftime('%d/%m/%Y às %H:%M')}",
        "criado_por": "sistema"
    })

    return consulta


@router.get("/", response_model=List[ConsultaOut])
def listar_consultas(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    data: Optional[date] = Query(None, description="Filtrar por data (YYYY-MM-DD)"),
    medico_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    paciente_id: Optional[UUID] = Query(None),
    limit: int = Query(100, le=500)
):
    query = db.table("consultas").select("*, pacientes(nome, telefone), medicos(nome, especialidade)") \
        .eq("clinica_id", clinica_id)

    if data:
        inicio = f"{data}T00:00:00"
        fim    = f"{data}T23:59:59"
        query  = query.gte("data_hora", inicio).lte("data_hora", fim)
    if medico_id:
        query = query.eq("medico_id", str(medico_id))
    if status:
        query = query.eq("status", status)
    if paciente_id:
        query = query.eq("paciente_id", str(paciente_id))

    res = query.order("data_hora").limit(limit).execute()
    return res.data


@router.patch("/{consulta_id}", response_model=ConsultaOut)
def atualizar_consulta(
    consulta_id: UUID,
    body: ConsultaUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "data_hora" in data:
        data["data_hora"] = data["data_hora"].isoformat()

    res = db.table("consultas") \
        .update(data) \
        .eq("id", str(consulta_id)) \
        .eq("clinica_id", clinica_id) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    consulta = res.data[0]

    # Se o status mudou, registra na timeline
    if body.status:
        registrar_interacao(db, {
            "clinica_id": clinica_id,
            "paciente_id": consulta["paciente_id"],
            "tipo": "consulta",
            "conteudo": f"Status da consulta atualizado para: {body.status}",
            "criado_por": "sistema"
        })

    return consulta


@router.get("/agenda-do-dia", response_model=List[ConsultaOut])
def agenda_hoje(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    medico_id: Optional[UUID] = Query(None)
):
    hoje = datetime.now(timezone.utc).date()
    inicio = f"{hoje}T00:00:00"
    fim    = f"{hoje}T23:59:59"

    query = db.table("consultas") \
        .select("*, pacientes(nome, telefone), medicos(nome, especialidade)") \
        .eq("clinica_id", clinica_id) \
        .gte("data_hora", inicio) \
        .lte("data_hora", fim)

    if medico_id:
        query = query.eq("medico_id", str(medico_id))

    return query.order("data_hora").limit(200).execute().data
