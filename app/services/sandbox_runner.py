"""
sandbox_runner.py — Runs WhatsAppAgent with zero production side effects.

Write tools are intercepted and return fake "simulated" results.
Read tools (search_kb, buscar_medicos, verificar_slots) execute for real
against the clinic's actual data, so KB and calendar responses are accurate.

Usage
-----
    result = await run_sandbox(
        db=db,
        clinica_id=clinica_id,
        messages=[{"role": "user", "content": "Quanto custa botox?"}],
        contact_scenario="new_lead",
        simulate_tools=True,
        playbook={...},
    )
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from app.agents.whatsapp_agent import WhatsAppAgent
from app.core.config import settings
from app.services.prompt_builder import (
    default_snapshot,
    detect_stage_from_response,
    format_playbook_block,
    format_profile_block,
    format_snapshot_block,
    get_blocked_tools,
)
from app.services.agent_health_service import detect_flags
from app.services.wa_chunker import split_into_chunks

logger = logging.getLogger(__name__)

# ─── Write tools that are intercepted in sandbox ──────────────────────────────

_WRITE_TOOLS: set[str] = {
    "agendar_consulta",
    "cancelar_consulta",
    "escalar_para_humano",
    "registrar_consentimento_rgpd",
}

_SIMULATED_RESULTS: dict[str, Any] = {
    "agendar_consulta":             lambda inp: {
        "simulated": True,
        "booking_id": "FAKE-001",
        "status": "agendada",
        "data_hora": inp.get("data_hora", "2026-07-01T10:00:00"),
        "tipo": inp.get("tipo", "primeira_vez"),
    },
    "cancelar_consulta":            lambda inp: {
        "simulated": True,
        "message": f"Consulta {inp.get('consulta_id', '?')} cancelada (simulação).",
    },
    "escalar_para_humano":          lambda inp: {
        "simulated": True,
        "message": f"Caso escalado (simulação): {inp.get('motivo', '')}",
    },
    "registrar_consentimento_rgpd": lambda _: {
        "simulated": True,
        "message": "Consentimento de privacidade registado (simulação).",
    },
}

# ─── Cost table (USD per 1M tokens, approximate) ─────────────────────────────

_PRICE_PER_1M: dict[str, dict[str, float]] = {
    "claude-opus-4-6":    {"in": 15.0,   "out": 75.0},
    "claude-opus-4-8":    {"in": 15.0,   "out": 75.0},
    "claude-sonnet-4-6":  {"in":  3.0,   "out": 15.0},
    "claude-haiku-4-5":   {"in":  0.25,  "out":  1.25},
    "claude-haiku-4-5-20251001": {"in": 0.25, "out": 1.25},
}
_DEFAULT_PRICE = {"in": 15.0, "out": 75.0}


def _cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p = _PRICE_PER_1M.get(model, _DEFAULT_PRICE)
    return (in_tok * p["in"] + out_tok * p["out"]) / 1_000_000


# ─── Contact scenarios ────────────────────────────────────────────────────────

_FAKE_CLINICA_ID_PLACEHOLDER = "00000000-sandbox-0000-0000-sandbox000"

def _build_scenario(scenario: str, clinica_id: str) -> dict:
    """
    Returns {paciente, ai_profile, context_snapshot} for the given scenario.
    The fake paciente uses the real clinica_id so read tools work correctly.
    """
    base_paciente = {
        "clinica_id": clinica_id,
        "status": "lead",
        "origem": "whatsapp",
        "tags": [],
        "consentimento_privacidade_at": None,
        "notas": None,
    }

    if scenario == "returning_patient":
        ai_profile: dict = {
            "preferences": {
                "preferred_procedures": ["botox"],
                "preferred_days": ["segunda", "quarta"],
                "preferred_time": "manhã",
            },
            "history_summary": "Paciente com 2 consultas anteriores. Interessada em botox labial. Gosta de comunicação descontraída.",
            "last_objection": None,
            "communication_style": "casual",
            "total_consultations": 2,
            "last_seen": "2026-05-15T10:00:00+00:00",
        }
        snap = default_snapshot()
        paciente = {
            **base_paciente,
            "id": "00000000-0000-0000-0000-sandbox000002",
            "nome": "Ana Silva [Sandbox]",
            "telefone": "sandbox-returning",
            "ai_profile": ai_profile,
        }

    elif scenario == "hot_lead":
        ai_profile = {
            "preferences": {"preferred_procedures": ["botox"], "preferred_days": ["segunda"], "preferred_time": "manhã"},
            "history_summary": "Lead quente — procedimento confirmado, procura horário.",
            "last_objection": None,
            "communication_style": "casual",
            "total_consultations": 0,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }
        snap = {
            "stage": "qualification",
            "mood": "curious",
            "intent": "scheduling",
            "last_intent_at": datetime.now(timezone.utc).isoformat(),
            "next_action": "offer_slots",
            "facts_captured": {
                "procedure_interest": "botox",
                "preferred_day": "segunda",
                "budget_mentioned": True,
            },
            "turns_in_stage": 1,
        }
        paciente = {
            **base_paciente,
            "id": "00000000-0000-0000-0000-sandbox000003",
            "nome": "Carlos Pereira [Sandbox]",
            "telefone": "sandbox-hot",
            "status": "lead",
            "ai_profile": ai_profile,
        }

    else:  # new_lead (default)
        ai_profile = {}
        snap = default_snapshot()
        paciente = {
            **base_paciente,
            "id": "00000000-0000-0000-0000-sandbox000001",
            "nome": "Novo Paciente [Sandbox]",
            "telefone": "sandbox-new",
            "ai_profile": ai_profile,
        }

    return {"paciente": paciente, "ai_profile": ai_profile, "context_snapshot": snap}


# ─── Guardrail checks ─────────────────────────────────────────────────────────

def _check_guardrails(tool_log: list[dict], response: str) -> list[str]:
    flags: list[str] = []
    tool_names = [t["tool"] for t in tool_log]

    # G3 risk: booking without prior slot check
    if "agendar_consulta" in tool_names:
        idx = tool_names.index("agendar_consulta")
        if "verificar_slots" not in tool_names[:idx]:
            flags.append("G3_RISK: agendar_consulta sem verificar_slots prévio")

    # KB skip: price mentioned without searching KB
    price_words = ["preço", "valor", "custo", "R$", "reais", "euros", "€"]
    if any(w in response for w in price_words) and "search_kb" not in tool_names:
        flags.append("KB_SKIP: valores mencionados sem consultar KB primeiro")

    # Long response
    if len(response) > 800:
        flags.append(f"LONG_RESPONSE: {len(response)} chars (recomendado ≤ 500 antes do chunking)")

    return flags


# ─── Sandbox agent ────────────────────────────────────────────────────────────

class SandboxWhatsAppAgent(WhatsAppAgent):
    """
    WhatsAppAgent variant that intercepts write tools.
    Tracks every tool call (simulated or real) in _tool_log.
    """

    def __init__(self, simulate_tools: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.simulate_tools = simulate_tools
        self._tool_log: list[dict] = []

    async def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        is_write = tool_name in _WRITE_TOOLS
        simulated = self.simulate_tools and is_write

        if simulated:
            factory = _SIMULATED_RESULTS.get(tool_name, lambda _: {"simulated": True})
            raw_result = factory(tool_input)
            result_str = json.dumps(raw_result, ensure_ascii=False)
        else:
            raw = await super().execute_tool(tool_name, tool_input)
            result_str = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)

        self._tool_log.append({
            "tool": tool_name,
            "simulated": simulated,
            "result_preview": result_str[:150],
        })
        return result_str

    async def _on_g3_violation(self, attempted: str, required: str) -> None:
        logger.warning("[SANDBOX] G3 gate | attempted=%s required=%s", attempted, required)


# ─── Public entry point ───────────────────────────────────────────────────────

async def run_sandbox(
    db: Client,
    clinica_id: str,
    messages: list[dict],
    contact_scenario: str,
    simulate_tools: bool,
    playbook: dict,
) -> dict:
    """
    Runs the WhatsApp agent in sandbox mode.
    Returns a rich structured result — no production DB writes (write tools simulated).
    """
    t_start = time.monotonic()

    # ── 1. Scenario ──────────────────────────────────────────────────────────
    scenario   = _build_scenario(contact_scenario, clinica_id)
    paciente   = scenario["paciente"]
    snapshot   = scenario["context_snapshot"]
    ai_profile = scenario["ai_profile"]
    stage_before = snapshot.get("stage", "opening")

    # ── 2. System prompt ─────────────────────────────────────────────────────
    last_msg     = messages[-1].get("content", "") if messages else ""
    blocked      = get_blocked_tools(playbook, stage_before)
    profile_blk  = format_profile_block(paciente.get("nome", "Paciente"), ai_profile)
    snapshot_blk = format_snapshot_block(snapshot)
    playbook_blk = format_playbook_block(playbook, stage_before, last_msg)
    extra_system = "\n\n".join(b for b in [profile_blk, snapshot_blk, playbook_blk] if b)

    # ── 3. Create sandbox agent ───────────────────────────────────────────────
    agent = SandboxWhatsAppAgent(
        simulate_tools=simulate_tools,
        paciente=paciente,
        clinica_id=clinica_id,
        db=db,
        pais="PT",
        blocked_tools=blocked or None,
        conversation_id="sandbox",
    )

    # ── 4. Inject history (if multi-turn) ────────────────────────────────────
    for msg in messages[:-1]:
        role    = msg.get("role", "user")
        content = msg.get("content", "")
        agent._history.append({"role": role, "content": content})

    # ── 5. Run ────────────────────────────────────────────────────────────────
    response_text = await agent.run(last_msg, extra_system=extra_system)
    latency_ms    = int((time.monotonic() - t_start) * 1000)

    # ── 6. Post-processing ────────────────────────────────────────────────────
    chunks           = split_into_chunks(response_text)
    updated_snapshot = detect_stage_from_response(response_text, last_msg, snapshot)
    stage_after      = updated_snapshot.get("stage", stage_before)

    in_tok  = agent._last_run_input_tokens
    out_tok = agent._last_run_output_tokens
    cost    = _cost_usd(agent.model, in_tok, out_tok)

    guardrails   = _check_guardrails(agent._tool_log, response_text)
    quality_flags = detect_flags(agent._tool_log, response_text)

    # ── 7. Audit log (sandbox source — won't pollute production metrics) ──────
    try:
        db.table("wa_agent_runs").insert({
            "clinica_id":         clinica_id,
            "source":             "sandbox",
            "agent_model":        agent.model,
            "input_tokens":       in_tok,
            "output_tokens":      out_tok,
            "cost_usd":           round(cost, 6),
            "latency_ms":         latency_ms,
            "tools_called":       agent._tool_log,
            "stage_before":       stage_before,
            "stage_after":        stage_after,
            # Quality flags (searchable in health dashboard)
            "kb_miss":            quality_flags["kb_miss"],
            "hallucination_flag": quality_flags["hallucination_flag"],
            "handover_triggered": quality_flags["handover_triggered"],
            "pii_blocked":        quality_flags["pii_blocked"],
            "metadata": {
                "scenario":        contact_scenario,
                "simulate_tools":  simulate_tools,
                "guardrail_flags": guardrails,
            },
        }).execute()
    except Exception:
        logger.exception("[SANDBOX] audit log insert failed")

    return {
        "reply_chunks":           chunks,
        "tools_called":           agent._tool_log,
        "stage_after":            stage_after,
        "context_snapshot_after": updated_snapshot,
        "cost_usd":               round(cost, 6),
        "tokens":                 {"in": in_tok, "out": out_tok},
        "latency_ms":             latency_ms,
        "guardrail_flags":        guardrails,
        "quality_flags":          quality_flags,
    }
