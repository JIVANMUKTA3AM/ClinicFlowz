"""
exportacao.py — Endpoints de portabilidade de dados pessoais.

Direito de portabilidade: LGPD (Brasil) · RGPD (Portugal)

Endpoints
---------
  GET /api/v1/exportacao/paciente/{paciente_id}
      Exporta todos os dados pessoais de um paciente (cadastro, consultas,
      interações, pipeline). Só devolve dados da clínica do JWT.

  GET /api/v1/exportacao/clinica
      Exporta os dados de configuração da própria clínica (médicos, salas,
      contagens de pacientes/consultas). Não inclui dados clínicos individuais.

Auditoria
---------
  Cada exportação grava um registo em exportacoes_auditoria com:
    user_id, user_email, tipo, paciente_id (quando aplicável), exportado_at.
  Isto é obrigatório pela LGPD (art. 37) e RGPD (art. 30).

Isolamento multi-tenant
-----------------------
  Todos os queries usam .eq("clinica_id", clinica_id) extraído do JWT.
  Nenhum dado de outra clínica é acessível.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.core.database import get_supabase, get_clinica_id, get_current_user
from app.core.locale import get_locale

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Audit helper ─────────────────────────────────────────────────────────────

def _registar_auditoria(
    db: Client,
    *,
    clinica_id: str,
    user: dict,
    tipo: str,
    paciente_id: str | None = None,
) -> None:
    """Grava registo de auditoria em exportacoes_auditoria."""
    try:
        row: dict = {
            "clinica_id":  clinica_id,
            "user_id":     user["sub"],
            "user_email":  user.get("email"),
            "tipo":        tipo,
            "exportado_at": datetime.now(timezone.utc).isoformat(),
        }
        if paciente_id:
            row["paciente_id"] = paciente_id
        db.table("exportacoes_auditoria").insert(row).execute()
    except Exception:
        # Auditoria nunca deve impedir a exportação.
        logger.exception("Falha ao registar auditoria de exportação | tipo=%s", tipo)


# ─── Locale helper ────────────────────────────────────────────────────────────

def _get_pais_clinica(db: Client, clinica_id: str) -> str:
    """Resolve pais da clínica a partir do DB. Devolve 'PT' por omissão."""
    try:
        res = db.table("clinicas").select("pais").eq("id", clinica_id).single().execute()
        return (res.data or {}).get("pais", "PT")
    except Exception:
        return "PT"


def _cabecalho_exportacao(lei: str, clinica_nome: str) -> dict:
    return {
        "versao":          "1.0",
        "lei_privacidade": lei,
        "clinica":         clinica_nome,
        "exportado_em":    datetime.now(timezone.utc).isoformat(),
        "nota": (
            f"Exportação de dados pessoais ao abrigo do direito de portabilidade "
            f"previsto na {lei}. Os dados são fornecidos no formato JSON (ISO 8601 "
            f"para datas, UTF-8 para texto)."
        ),
    }


# ─── Endpoint: paciente ───────────────────────────────────────────────────────

@router.get("/paciente/{paciente_id}")
def exportar_paciente(
    paciente_id: UUID,
    clinica_id: str   = Depends(get_clinica_id),
    user: dict        = Depends(get_current_user),
    db: Client        = Depends(get_supabase),
):
    """
    Exporta todos os dados pessoais de um paciente.

    Escopo: apenas o paciente cujo clinica_id corresponde ao JWT.
    Devolve 404 se o paciente não existir ou pertencer a outra clínica.
    """
    pid = str(paciente_id)

    # ── 1. Dados do paciente ──────────────────────────────────────────────────
    pac_res = (
        db.table("pacientes")
        .select("*")
        .eq("id", pid)
        .eq("clinica_id", clinica_id)   # isolamento tenant
        .single()
        .execute()
    )
    if not pac_res.data:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    paciente = pac_res.data

    # ── 2. Consultas ──────────────────────────────────────────────────────────
    consultas_res = (
        db.table("consultas")
        .select("id, data_hora, tipo, status, valor, forma_pagamento, pago, observacoes, created_at, medicos(nome, especialidade)")
        .eq("paciente_id", pid)
        .eq("clinica_id", clinica_id)
        .order("data_hora", desc=True)
        .execute()
    )

    # ── 3. Interações / timeline ──────────────────────────────────────────────
    interacoes_res = (
        db.table("interacoes")
        .select("id, tipo, direcao, conteudo, criado_por, created_at")
        .eq("paciente_id", pid)
        .eq("clinica_id", clinica_id)
        .order("created_at", desc=True)
        .execute()
    )

    # ── 4. Pipeline ───────────────────────────────────────────────────────────
    pipeline_res = (
        db.table("pipeline")
        .select("etapa, valor_estimado, observacoes, etapa_updated_at, created_at")
        .eq("paciente_id", pid)
        .eq("clinica_id", clinica_id)
        .limit(1)
        .execute()
    )

    # ── 5. Resolve locale ─────────────────────────────────────────────────────
    pais = _get_pais_clinica(db, clinica_id)
    loc  = get_locale(pais)

    clinica_nome_res = db.table("clinicas").select("nome").eq("id", clinica_id).single().execute()
    clinica_nome = (clinica_nome_res.data or {}).get("nome", "Clínica")

    # ── 6. Auditoria ──────────────────────────────────────────────────────────
    _registar_auditoria(db, clinica_id=clinica_id, user=user, tipo="paciente", paciente_id=pid)

    logger.info(
        "Exportação de dados pessoais | tipo=paciente | paciente=%s | clinica=%s | user=%s",
        pid, clinica_id, user["sub"],
    )

    # ── 7. Monta payload ─────────────────────────────────────────────────────
    return {
        "exportacao": _cabecalho_exportacao(loc.lei_privacidade, clinica_nome),
        "paciente": {
            "id":                         paciente.get("id"),
            "nome":                       paciente.get("nome"),
            "telefone":                   paciente.get("telefone"),
            "email":                      paciente.get("email"),
            "documento_fiscal":           paciente.get("documento_fiscal"),
            "data_nascimento":            paciente.get("data_nascimento"),
            "genero":                     paciente.get("genero"),
            "origem":                     paciente.get("origem"),
            "status":                     paciente.get("status"),
            "tags":                       paciente.get("tags", []),
            "notas":                      paciente.get("notas"),
            "consentimento_privacidade_at": paciente.get("consentimento_privacidade_at"),
            "criado_em":                  paciente.get("created_at"),
            "atualizado_em":              paciente.get("updated_at"),
            f"documento_fiscal_label":    loc.doc_fiscal_paciente_label,
        },
        "consultas": consultas_res.data or [],
        "interacoes": interacoes_res.data or [],
        "pipeline": (pipeline_res.data or [None])[0],
        "totais": {
            "consultas":  len(consultas_res.data or []),
            "interacoes": len(interacoes_res.data or []),
        },
    }


# ─── Endpoint: clínica ────────────────────────────────────────────────────────

@router.get("/clinica")
def exportar_clinica(
    clinica_id: str = Depends(get_clinica_id),
    user: dict      = Depends(get_current_user),
    db: Client      = Depends(get_supabase),
):
    """
    Exporta os dados de configuração da clínica (não inclui PII de pacientes).

    Inclui: dados da clínica, lista de médicos, salas, conexões WhatsApp,
    e contagens agregadas de pacientes/consultas.
    """
    # ── 1. Dados da clínica ───────────────────────────────────────────────────
    clinica_res = (
        db.table("clinicas")
        .select("*")
        .eq("id", clinica_id)
        .single()
        .execute()
    )
    if not clinica_res.data:
        raise HTTPException(status_code=404, detail="Clínica não encontrada")

    clinica = clinica_res.data
    pais    = clinica.get("pais", "PT")
    loc     = get_locale(pais)

    # ── 2. Médicos ────────────────────────────────────────────────────────────
    medicos_res = (
        db.table("medicos")
        .select("id, nome, especialidade, cedula, email, telefone, comissao_pct, ativo, created_at")
        .eq("clinica_id", clinica_id)
        .order("nome")
        .execute()
    )

    # ── 3. Salas ──────────────────────────────────────────────────────────────
    salas_res = (
        db.table("salas")
        .select("id, nome, descricao, ativa")
        .eq("clinica_id", clinica_id)
        .execute()
    )

    # ── 4. Conexões WhatsApp (sem keys) ───────────────────────────────────────
    wa_res = (
        db.table("whatsapp_connections")
        .select("id, instance_name, phone_number, ativo, created_at")
        .eq("clinica_id", clinica_id)
        .execute()
    )

    # ── 5. Contagens agregadas ────────────────────────────────────────────────
    total_pacientes = len(
        (db.table("pacientes").select("id").eq("clinica_id", clinica_id).execute().data or [])
    )
    total_consultas = len(
        (db.table("consultas").select("id").eq("clinica_id", clinica_id).execute().data or [])
    )

    # ── 6. Auditoria ──────────────────────────────────────────────────────────
    _registar_auditoria(db, clinica_id=clinica_id, user=user, tipo="clinica")

    logger.info(
        "Exportação de dados | tipo=clinica | clinica=%s | user=%s",
        clinica_id, user["sub"],
    )

    # ── 7. Monta payload ─────────────────────────────────────────────────────
    return {
        "exportacao": _cabecalho_exportacao(loc.lei_privacidade, clinica.get("nome", "")),
        "clinica": {
            "id":               clinica.get("id"),
            "nome":             clinica.get("nome"),
            "documento_fiscal": clinica.get("documento_fiscal"),
            f"documento_fiscal_label": loc.doc_fiscal_clinica_label,
            "email":            clinica.get("email"),
            "telefone":         clinica.get("telefone"),
            "morada":           clinica.get("morada"),
            "cidade":           clinica.get("cidade"),
            "pais":             clinica.get("pais"),
            "plano":            clinica.get("plano"),
            "ativo":            clinica.get("ativo"),
            "criado_em":        clinica.get("created_at"),
            "lei_privacidade":  loc.lei_privacidade,
            "moeda":            loc.moeda,
        },
        "medicos":               medicos_res.data or [],
        "salas":                 salas_res.data or [],
        "whatsapp_connections":  wa_res.data or [],
        "totais": {
            "medicos":    len(medicos_res.data or []),
            "salas":      len(salas_res.data or []),
            "pacientes":  total_pacientes,
            "consultas":  total_consultas,
        },
    }
