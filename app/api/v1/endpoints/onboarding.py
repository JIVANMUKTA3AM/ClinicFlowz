from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_supabase, get_current_user
from app.core.locale import validar_documento_fiscal
from supabase import Client

router = APIRouter()


class OnboardingBody(BaseModel):
    pais: str                              # "PT" | "BR" — obrigatório
    clinica_nome: str
    clinica_documento_fiscal: Optional[str] = None
    clinica_telefone: Optional[str] = None
    clinica_email: Optional[str] = None
    clinica_morada: Optional[str] = None
    clinica_cidade: Optional[str] = None


class OnboardingResponse(BaseModel):
    clinica_id: str


@router.post("/", response_model=OnboardingResponse, status_code=201)
def criar_clinica_onboarding(
    body: OnboardingBody,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase),
):
    pais = body.pais.upper()
    if pais not in ("PT", "BR"):
        raise HTTPException(status_code=422, detail="País inválido. Use 'PT' ou 'BR'.")

    if user.get("user_metadata", {}).get("clinica_id"):
        raise HTTPException(status_code=400, detail="Clínica já configurada para este utilizador")

    if body.clinica_documento_fiscal:
        try:
            validar_documento_fiscal(body.clinica_documento_fiscal, pais, "clinica")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    res = db.table("clinicas").insert({
        "nome":             body.clinica_nome,
        "documento_fiscal": body.clinica_documento_fiscal,
        "telefone":         body.clinica_telefone,
        "email":            body.clinica_email,
        "morada":           body.clinica_morada,
        "cidade":           body.clinica_cidade,
        "pais":             pais,
        "plano":            "starter",
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar clínica")

    clinica_id = str(res.data[0]["id"])

    try:
        db.auth.admin.update_user_by_id(
            user["sub"],
            {"user_metadata": {"clinica_id": clinica_id, "pais": pais}},
        )
    except Exception as e:
        db.table("clinicas").delete().eq("id", clinica_id).execute()
        raise HTTPException(status_code=500, detail=f"Erro ao configurar utilizador: {e}")

    return {"clinica_id": clinica_id}
