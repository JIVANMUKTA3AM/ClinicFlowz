"""
retention.py — Proactive patient retention endpoint.

POST /api/v1/retention/run triggers the RetentionAgent for one patient (targeted)
or discovers eligible patients automatically (batch).

Patient discovery per campaign
-------------------------------
  POST_CONSULTATION     Last realizada or falta consultation within 1–3 days.
                        Covers both: follow-up after visit AND no-show recovery.

  CHECKUP_REMINDER      Active patients whose last realizada consultation was
                        between 180 and 364 days ago.

  REACTIVATION          Patients absent for 365+ days, or status='inativo',
                        with no recent re-engagement interaction.

  INCOMPLETE_TREATMENT  Patients in pipeline stage 'orcamento' or
                        'tratamento_ativo' whose last realizada consultation
                        was more than 30 days ago.

Pipeline integration
--------------------
  A successful engagement for CHECKUP_REMINDER/REACTIVATION updates the
  patient's status from 'inativo' → 'ativo' and records the engagement
  in the interacoes timeline.

Multi-tenancy
-------------
  All queries are scoped to clinica_id from the JWT. The service key is used
  for Supabase access (bypasses RLS), but clinica_id is always injected
  explicitly — no cross-tenant data leaks possible.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.agents.retention_agent import RetentionCampaign
from app.core.database import get_clinica_id, get_supabase
from app.schemas.schemas import (
    RetentionResultItem,
    RetentionRunRequest,
    RetentionRunResponse,
)
from app.services.agent_dispatcher import SupabaseRetentionAgent

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Public endpoint ──────────────────────────────────────────────────────────

@router.post("/run", response_model=RetentionRunResponse)
async def run_retention(
    body: RetentionRunRequest,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    """
    Triggers the RetentionAgent for one patient or a batch of eligible patients.

    **Single mode** — supply `paciente_id` to target a specific patient.

    **Batch mode** — omit `paciente_id`; the system discovers up to `limite`
    eligible patients based on the campaign criteria.

    Each patient runs through the full agentic loop: the model fetches the
    patient history, composes a personalised WhatsApp message, optionally
    schedules a follow-up, and logs the engagement result.
    """
    try:
        campanha = RetentionCampaign(body.campanha)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Campanha inválida: '{body.campanha}'. "
                f"Valores aceites: {[c.value for c in RetentionCampaign]}"
            ),
        )

    # ── Discover patients ────────────────────────────────────────────────────
    if body.paciente_id:
        pacientes = _buscar_paciente_por_id(db, clinica_id, str(body.paciente_id))
        if not pacientes:
            raise HTTPException(
                status_code=404,
                detail=f"Paciente {body.paciente_id} não encontrado nesta clínica.",
            )
    else:
        pacientes = _descobrir_pacientes(db, clinica_id, campanha, body.limite)

    if not pacientes:
        return RetentionRunResponse(
            total_processados=0,
            total_sucesso=0,
            total_falha=0,
            resultados=[],
        )

    logger.info(
        "retention/run | campanha=%s clinica=%s pacientes=%d",
        campanha.value,
        clinica_id,
        len(pacientes),
    )

    # ── Run agent for each patient ───────────────────────────────────────────
    resultados: list[RetentionResultItem] = []

    for paciente in pacientes:
        result = await _executar_para_paciente(paciente, clinica_id, db, campanha)
        resultados.append(result)

        # Pipeline: if engagement succeeded, ensure patient is marked ativo
        if result.sucesso:
            _atualizar_status_pos_engajamento(db, paciente, clinica_id, campanha)

    sucesso_count = sum(1 for r in resultados if r.sucesso)
    falha_count = len(resultados) - sucesso_count

    logger.info(
        "retention/run finished | campanha=%s clinica=%s sucesso=%d falha=%d",
        campanha.value,
        clinica_id,
        sucesso_count,
        falha_count,
    )

    return RetentionRunResponse(
        total_processados=len(resultados),
        total_sucesso=sucesso_count,
        total_falha=falha_count,
        resultados=resultados,
    )


# ─── Patient discovery ────────────────────────────────────────────────────────

def _buscar_paciente_por_id(
    db: Client,
    clinica_id: str,
    paciente_id: str,
) -> list[dict]:
    res = (
        db.table("pacientes")
        .select("*")
        .eq("id", paciente_id)
        .eq("clinica_id", clinica_id)
        .execute()
    )
    return res.data or []


def _descobrir_pacientes(
    db: Client,
    clinica_id: str,
    campanha: RetentionCampaign,
    limite: int,
) -> list[dict]:
    """
    Discovers eligible patients for a given campaign.

    Strategy
    --------
    1. Fetch all realizada/falta consultations for the clinic (ordered desc).
    2. Keep only the *latest* consultation per patient.
    3. Apply campaign-specific date filters in Python.
    4. Fetch the full patient records for the filtered IDs.

    This approach avoids complex SQL subqueries while remaining correct for
    clinic sizes up to ~10 000 patients.
    """
    hoje = datetime.now(timezone.utc)

    # ── Fetch last consultation per patient ──────────────────────────────────
    consultas_res = (
        db.table("consultas")
        .select("paciente_id, data_hora, status, tipo")
        .eq("clinica_id", clinica_id)
        .in_("status", ["realizada", "falta"])
        .order("data_hora", desc=True)
        .execute()
    )

    # Keep only the most recent consultation per patient
    ultima: dict[str, dict] = {}
    for c in (consultas_res.data or []):
        pid = c["paciente_id"]
        if pid not in ultima:
            ultima[pid] = c

    # ── Campaign filters ─────────────────────────────────────────────────────
    paciente_ids: list[str] = []

    if campanha == RetentionCampaign.POST_CONSULTATION:
        # Last visit (realizada OR falta) within 1–3 days ago
        cutoff_near = hoje - timedelta(days=1)
        cutoff_far  = hoje - timedelta(days=3)
        for pid, c in ultima.items():
            dt = _parse_dt(c["data_hora"])
            if dt and cutoff_far <= dt <= cutoff_near:
                paciente_ids.append(pid)

    elif campanha == RetentionCampaign.CHECKUP_REMINDER:
        # Last realizada 180–364 days ago (already due but not yet a year)
        cutoff_near = hoje - timedelta(days=180)
        cutoff_far  = hoje - timedelta(days=364)
        for pid, c in ultima.items():
            if c["status"] != "realizada":
                continue
            dt = _parse_dt(c["data_hora"])
            if dt and cutoff_far <= dt <= cutoff_near:
                paciente_ids.append(pid)

    elif campanha == RetentionCampaign.REACTIVATION:
        # Last realizada 365+ days ago — or status inativo regardless of date
        cutoff = hoje - timedelta(days=365)
        active_ids_from_consultas = set()
        for pid, c in ultima.items():
            if c["status"] != "realizada":
                continue
            dt = _parse_dt(c["data_hora"])
            if dt and dt < cutoff:
                active_ids_from_consultas.add(pid)

        # Also pick up patients explicitly marked inativo (may have no consultations)
        inativo_res = (
            db.table("pacientes")
            .select("id")
            .eq("clinica_id", clinica_id)
            .eq("status", "inativo")
            .execute()
        )
        inativos = {r["id"] for r in (inativo_res.data or [])}
        paciente_ids = list(active_ids_from_consultas | inativos)

    elif campanha == RetentionCampaign.INCOMPLETE_TREATMENT:
        # Pipeline in orcamento/tratamento_ativo and last realizada > 30 days ago
        pipeline_res = (
            db.table("pipeline")
            .select("paciente_id")
            .eq("clinica_id", clinica_id)
            .in_("etapa", ["orcamento", "tratamento_ativo"])
            .execute()
        )
        pipeline_ids = {r["paciente_id"] for r in (pipeline_res.data or [])}

        cutoff = hoje - timedelta(days=30)
        for pid in pipeline_ids:
            c = ultima.get(pid)
            if c is None:
                # No consultation at all — definitely eligible
                paciente_ids.append(pid)
                continue
            if c["status"] != "realizada":
                continue
            dt = _parse_dt(c["data_hora"])
            if dt and dt < cutoff:
                paciente_ids.append(pid)

    if not paciente_ids:
        return []

    # ── Fetch full patient records (batch, one query) ─────────────────────────
    paciente_ids = paciente_ids[:limite]
    res = (
        db.table("pacientes")
        .select("*")
        .in_("id", paciente_ids)
        .eq("clinica_id", clinica_id)
        .neq("status", "arquivado")
        .execute()
    )
    return res.data or []


# ─── Agent execution ──────────────────────────────────────────────────────────

async def _executar_para_paciente(
    paciente: dict,
    clinica_id: str,
    db: Client,
    campanha: RetentionCampaign,
) -> RetentionResultItem:
    patient_id: str = paciente["id"]
    patient_name: str = paciente.get("nome", "Paciente")

    logger.info(
        "retention | engage start | patient=%s campanha=%s",
        patient_id,
        campanha.value,
    )

    try:
        agent = SupabaseRetentionAgent(
            paciente=paciente,
            clinica_id=clinica_id,
            db=db,
        )
        await agent.engage(patient_id, campanha)

        result = agent.engagement_result
        if result is None:
            raise RuntimeError("Agent finalised without calling log_engagement_result.")

        logger.info(
            "retention | engage ok | patient=%s actions=%s",
            patient_id,
            [a.value for a in result.actions_taken],
        )
        return RetentionResultItem(
            paciente_id=patient_id,
            paciente_nome=patient_name,
            campanha=campanha.value,
            actions_taken=[a.value for a in result.actions_taken],
            message_preview=result.message_preview,
            summary=result.summary,
            sucesso=True,
        )

    except Exception as exc:
        logger.exception(
            "retention | engage failed | patient=%s campanha=%s",
            patient_id,
            campanha.value,
        )
        return RetentionResultItem(
            paciente_id=patient_id,
            paciente_nome=patient_name,
            campanha=campanha.value,
            actions_taken=[],
            message_preview="",
            summary="",
            sucesso=False,
            erro=str(exc),
        )


# ─── Pipeline / status side-effects ──────────────────────────────────────────

def _atualizar_status_pos_engajamento(
    db: Client,
    paciente: dict,
    clinica_id: str,
    campanha: RetentionCampaign,
) -> None:
    """
    After a successful engagement:
    • Reactivation / CheckupReminder: flip inativo → ativo so the patient
      re-enters the active cohort for future queries.
    • IncompleteT reatment: record an interaction note so the clinic team can
      see the outreach was made (pipeline stage is updated by the agent itself
      via suggest_followup if warranted).
    """
    patient_id = paciente["id"]

    if campanha in (RetentionCampaign.REACTIVATION, RetentionCampaign.CHECKUP_REMINDER):
        if paciente.get("status") == "inativo":
            db.table("pacientes").update({"status": "ativo"}).eq(
                "id", patient_id
            ).eq("clinica_id", clinica_id).execute()

            db.table("interacoes").insert({
                "clinica_id": clinica_id,
                "paciente_id": patient_id,
                "tipo": "nota",
                "conteudo": (
                    f"[REATIVAÇÃO] Paciente reactivado após campanha "
                    f"{campanha.value}."
                ),
                "criado_por": "sistema",
            }).execute()

            logger.info(
                "retention | patient reactivated | patient=%s",
                patient_id,
            )

    elif campanha == RetentionCampaign.INCOMPLETE_TREATMENT:
        # Record that outreach was attempted — clinic team decides next step
        db.table("interacoes").insert({
            "clinica_id": clinica_id,
            "paciente_id": patient_id,
            "tipo": "nota",
            "conteudo": (
                "[TRATAMENTO INCOMPLETO] Contacto de retenção enviado. "
                "Aguarda resposta do paciente."
            ),
            "criado_por": "sistema",
        }).execute()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _parse_dt(value: str) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string; returns None on failure."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
