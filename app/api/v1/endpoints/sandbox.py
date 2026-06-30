"""
sandbox.py — Sandbox endpoint: roda o agente completo sem efeitos colaterais.

POST /api/v1/sandbox/run
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from supabase import Client

from app.core.database import get_clinica_id, get_supabase
from app.services.sandbox_runner import run_sandbox

router = APIRouter()


# ─── Schema ───────────────────────────────────────────────────────────────────

class SandboxMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str


class SandboxRequest(BaseModel):
    contact_scenario: Literal["new_lead", "returning_patient", "hot_lead"] = "new_lead"
    messages: list[SandboxMessage] = Field(..., min_length=1)
    simulate_tools: bool = True


class ToolCallRecord(BaseModel):
    tool: str
    simulated: bool
    result_preview: str


class SandboxResponse(BaseModel):
    reply_chunks: list[str]
    tools_called: list[dict]
    stage_after: str
    context_snapshot_after: dict
    cost_usd: float
    tokens: dict
    latency_ms: int
    guardrail_flags: list[str]


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/run", response_model=SandboxResponse)
async def sandbox_run(
    body: SandboxRequest,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """
    Runs the WhatsApp agent in sandbox mode for this clinic.

    - Read tools (search_kb, buscar_medicos, verificar_slots) query real data.
    - Write tools (agendar_consulta, etc.) return simulated results when simulate_tools=True.
    - Results are logged in wa_agent_runs with source='sandbox' (excluded from prod metrics).
    """
    # Load this clinic's playbook (real data — same as production)
    playbook: dict = {}
    try:
        res = (
            db.table("wa_agents")
            .select("agent_playbook")
            .eq("clinica_id", clinica_id)
            .eq("ativo", True)
            .limit(1)
            .execute()
        )
        if res.data:
            playbook = res.data[0].get("agent_playbook") or {}
    except Exception:
        pass  # run sandbox without playbook if unavailable

    return await run_sandbox(
        db=db,
        clinica_id=clinica_id,
        messages=[m.model_dump() for m in body.messages],
        contact_scenario=body.contact_scenario,
        simulate_tools=body.simulate_tools,
        playbook=playbook,
    )
