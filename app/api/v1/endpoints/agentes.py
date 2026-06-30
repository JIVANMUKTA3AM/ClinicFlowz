"""
agentes.py — CRUD de configuração do agente WhatsApp por clínica.

Cada clínica tem exatamente um agente (UNIQUE clinica_id em wa_agents).
O endpoint GET cria o registo com o playbook padrão se não existir.

Endpoints
---------
  GET  /agents/          — devolve (ou cria) a config do agente desta clínica
  PUT  /agents/{id}/playbook — actualiza agent_playbook
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.core.database import get_clinica_id, get_supabase
from app.services.agent_health_service import compute_metrics, fetch_runs

router = APIRouter()

# ─── Playbook padrão ──────────────────────────────────────────────────────────
# Usa os nomes reais das tools do WhatsAppAgent.

_DEFAULT_PLAYBOOK: dict = {
    "stages": [
        {
            "id": "opening",
            "label": "Acolhimento",
            "goals": [
                "Responder o que o paciente perguntou",
                "Pedir o nome após responder",
                "Detectar emoção e urgência",
            ],
            "probing_questions": [
                "Com quem falo?",
                "O que te trouxe até aqui hoje?",
            ],
            "advance_when": [
                "Mencionou procedimento de interesse",
                "Fez pergunta sobre preço",
                "Pediu agendamento",
            ],
            "min_turns": 1,
            "blocked_tools": ["agendar_consulta", "verificar_slots"],
        },
        {
            "id": "discovery",
            "label": "Entendendo a necessidade",
            "goals": [
                "Entender o procedimento de interesse",
                "Capturar preferência de dia/horário",
            ],
            "probing_questions": [
                "Qual procedimento tens interesse?",
                "Tens preferência de dia ou período?",
            ],
            "advance_when": [
                "Procedimento confirmado",
                "Preferência de horário mencionada",
            ],
            "min_turns": 1,
            "blocked_tools": ["agendar_consulta"],
        },
        {
            "id": "qualification",
            "label": "Qualificação",
            "goals": [
                "Verificar disponibilidade de horários",
                "Apresentar opções sem forçar",
            ],
            "probing_questions": [],
            "advance_when": [
                "Cliente confirmou interesse num horário",
                "Pediu para agendar",
            ],
            "min_turns": 1,
            "blocked_tools": [],
        },
        {
            "id": "scheduling",
            "label": "Agendamento",
            "goals": [
                "Confirmar dados do paciente",
                "Finalizar agendamento",
                "Enviar confirmação",
            ],
            "probing_questions": [],
            "advance_when": ["Agendamento confirmado"],
            "min_turns": 1,
            "blocked_tools": [],
        },
        {
            "id": "closing",
            "label": "Encerramento",
            "goals": [
                "Confirmar próximo passo",
                "Deixar porta aberta para contacto futuro",
            ],
            "probing_questions": [],
            "advance_when": [],
            "min_turns": 1,
            "blocked_tools": [],
        },
    ],
    "objections": [
        {
            "name": "preco",
            "patterns": ["caro", "muito dinheiro", "não tenho", "desconto", "parcelado", "valor"],
            "strategy": "Acolher sem pressionar. Explicar o valor da consulta. Oferecer avaliação gratuita como primeiro passo.",
            "next_action": "offer_evaluation",
        },
        {
            "name": "medo_artificial",
            "patterns": ["artificial", "natural", "exagerado", "estranho", "ficará", "parecer"],
            "strategy": "Validar o medo com empatia. Explicar a técnica conservadora da clínica. Mostrar que a avaliação não compromete.",
            "next_action": "offer_evaluation",
        },
    ],
}


# ─── Schema ───────────────────────────────────────────────────────────────────

class PlaybookUpdate(BaseModel):
    playbook: dict


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_or_create(db: Client, clinica_id: str) -> dict:
    res = (
        db.table("wa_agents")
        .select("*")
        .eq("clinica_id", clinica_id)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]

    created = db.table("wa_agents").insert({
        "clinica_id": clinica_id,
        "nome": "Agente WhatsApp",
        "ativo": True,
        "agent_playbook": _DEFAULT_PLAYBOOK,
    }).execute()

    if not created.data:
        raise HTTPException(status_code=500, detail="Erro ao criar configuração do agente.")
    return created.data[0]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/")
def get_agent(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """Devolve (ou inicializa com playbook padrão) a config do agente desta clínica."""
    return _get_or_create(db, clinica_id)


@router.put("/{agent_id}/playbook")
def update_playbook(
    agent_id: str,
    body: PlaybookUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """
    Actualiza o agent_playbook do agente.
    O agent_id é validado contra clinica_id para garantir isolamento tenant.
    """
    res = (
        db.table("wa_agents")
        .update({"agent_playbook": body.playbook})
        .eq("id", agent_id)
        .eq("clinica_id", clinica_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")
    return res.data[0]


@router.get("/health")
def get_health(
    period: str = Query("7d", pattern="^(7d|30d)$"),
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """
    Métricas de saúde do agente para o período especificado.
    Inclui runs de sandbox E produção (separados em sandbox_runs/production_runs).
    """
    days = 30 if period == "30d" else 7
    runs = fetch_runs(db, clinica_id, days)
    metrics = compute_metrics(runs)
    metrics["period"] = period
    return metrics
