from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID
from app.core.database import get_supabase, get_clinica_id
from app.core.locale import validar_documento_fiscal
from app.schemas.schemas import PacienteCreate, PacienteUpdate, PacienteOut
from supabase import Client
from datetime import datetime, timezone

router = APIRouter()

@router.post("/", response_model=PacienteOut, status_code=201)
def criar_paciente(
    body: PacienteCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    # Resolve pais da clínica para validação de documento fiscal
    clinica_res = db.table("clinicas").select("pais").eq("id", clinica_id).single().execute()
    pais = (clinica_res.data or {}).get("pais", "PT")

    if body.documento_fiscal:
        try:
            validar_documento_fiscal(body.documento_fiscal, pais, "paciente")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    data = body.model_dump(exclude={"consentimento_privacidade"})
    data["clinica_id"] = clinica_id
    if body.consentimento_privacidade:
        data["consentimento_privacidade_at"] = datetime.now(timezone.utc).isoformat()

    res = db.table("pacientes").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar paciente")
    return res.data[0]


@router.get("/", response_model=List[PacienteOut])
def listar_pacientes(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    status: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Busca por nome ou telefone"),
    limit: int = Query(50, le=200),
    offset: int = Query(0)
):
    query = db.table("pacientes").select("*").eq("clinica_id", clinica_id)

    if status:
        query = query.eq("status", status)
    if origem:
        query = query.eq("origem", origem)
    if tag:
        query = query.contains("tags", [tag])
    if q:
        query = query.or_(f"nome.ilike.%{q}%,telefone.ilike.%{q}%")

    res = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return res.data


@router.get("/{paciente_id}", response_model=PacienteOut)
def obter_paciente(
    paciente_id: UUID,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    res = db.table("pacientes") \
        .select("*") \
        .eq("id", str(paciente_id)) \
        .eq("clinica_id", clinica_id) \
        .single() \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    return res.data


@router.patch("/{paciente_id}", response_model=PacienteOut)
def atualizar_paciente(
    paciente_id: UUID,
    body: PacienteUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    res = db.table("pacientes") \
        .update(data) \
        .eq("id", str(paciente_id)) \
        .eq("clinica_id", clinica_id) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    return res.data[0]


@router.delete("/{paciente_id}", status_code=204)
def arquivar_paciente(
    paciente_id: UUID,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    """Soft delete — muda status para arquivado (dados não apagados imediatamente)."""
    db.table("pacientes") \
        .update({"status": "arquivado", "updated_at": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", str(paciente_id)) \
        .eq("clinica_id", clinica_id) \
        .execute()
