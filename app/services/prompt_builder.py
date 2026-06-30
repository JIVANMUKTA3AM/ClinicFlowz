"""
prompt_builder.py — Context snapshot formatting and stage detection.

Two responsibilities:
  1. format_snapshot_block(snapshot)  → markdown block injected in the system prompt
  2. detect_stage_from_response(response, patient_msg, snapshot) → updated snapshot

Stage detection is regex-only (zero LLM cost, < 1 ms). It covers the most
common transitions; ambiguous cases simply stay in the current stage until
a clearer signal arrives.

Conversation stages
-------------------
  opening      → patient just sent first message
  discovery    → agent is learning what the patient wants
  qualification → procedure identified, collecting details
  scheduling   → offering/confirming time slots
  closing      → booking confirmed or conversation ended
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# ─── Default snapshot ─────────────────────────────────────────────────────────

_DEFAULT_SNAPSHOT: dict[str, Any] = {
    "stage": "opening",
    "mood": "curious",
    "intent": "other",
    "last_intent_at": None,
    "next_action": "ask_procedure",
    "facts_captured": {
        "procedure_interest": None,
        "preferred_day": None,
        "budget_mentioned": False,
    },
    "turns_in_stage": 0,
}


def default_snapshot() -> dict:
    snap = dict(_DEFAULT_SNAPSHOT)
    snap["facts_captured"] = dict(_DEFAULT_SNAPSHOT["facts_captured"])
    return snap


# ─── ai_profile block (cross-conversation memory) ────────────────────────────

def format_profile_block(nome: str, ai_profile: dict) -> str:
    """
    Formats the persistent ai_profile into a system-prompt block.
    Returns an empty string when the profile is empty (first conversation)
    so no placeholder text is injected.
    """
    if not ai_profile:
        return ""

    prefs = ai_profile.get("preferences") or {}
    procedures = prefs.get("preferred_procedures") or []
    days       = prefs.get("preferred_days") or []
    time_pref  = prefs.get("preferred_time", "")
    summary    = ai_profile.get("history_summary", "")
    objection  = ai_profile.get("last_objection")
    style      = ai_profile.get("communication_style", "")
    last_seen  = (ai_profile.get("last_seen") or "")[:10]

    lines: list[str] = [f"## O que já sei sobre {nome}"]
    if summary:
        lines.append(f"- **Resumo**: {summary}")
    if procedures:
        lines.append(f"- **Procedimentos de interesse**: {', '.join(procedures)}")
    if days:
        lines.append(f"- **Dias preferidos**: {', '.join(days)}")
    if time_pref:
        lines.append(f"- **Horário preferido**: {time_pref}")
    if style:
        lines.append(f"- **Estilo de comunicação**: {style}")
    if objection:
        lines.append(f"- **Última objeção**: {objection}")
    if last_seen:
        lines.append(f"- **Última conversa**: {last_seen}")

    lines.append("\nAdapta a tua resposta ao perfil deste paciente.")
    return "\n".join(lines)


# ─── Context snapshot block (per-conversation state) ─────────────────────────

def format_snapshot_block(snapshot: dict) -> str:
    """
    Formats a context_snapshot dict into a markdown block for injection
    into the agent system prompt.

    The block is designed to be compact (stays under ~20 lines) so it
    doesn't bloat the system prompt token count.
    """
    if not snapshot:
        snapshot = default_snapshot()

    facts = snapshot.get("facts_captured") or {}
    facts_lines: list[str] = []
    if facts.get("procedure_interest"):
        facts_lines.append(f"  - Procedimento de interesse: **{facts['procedure_interest']}**")
    if facts.get("preferred_day"):
        facts_lines.append(f"  - Dia preferido: **{facts['preferred_day']}**")
    if facts.get("budget_mentioned"):
        facts_lines.append("  - Paciente já mencionou preço/orçamento")
    if not facts_lines:
        facts_lines.append("  - Ainda sem dados capturados")

    facts_str = "\n".join(facts_lines)
    turns = snapshot.get("turns_in_stage", 0)

    return (
        "## Estado atual da conversa\n"
        f"- **Stage**: {snapshot.get('stage', 'opening')} "
        f"({turns} turno{'s' if turns != 1 else ''} neste stage)\n"
        f"- **Mood do paciente**: {snapshot.get('mood', 'curious')}\n"
        f"- **Intenção detectada**: {snapshot.get('intent', 'other')}\n"
        f"- **Próxima ação recomendada**: {snapshot.get('next_action', 'ask_procedure')}\n"
        f"- **Dados já capturados**:\n{facts_str}\n\n"
        "Usa este contexto para manter coerência com o histórico da conversa. "
        "Não menciones estes estados internos explicitamente ao paciente."
    )


# ─── Playbook block (stage machine guidance) ──────────────────────────────────

# All tool names registered in WhatsAppAgent._TOOLS
_ALL_AGENT_TOOLS = [
    "buscar_medicos",
    "verificar_slots",
    "agendar_consulta",
    "cancelar_consulta",
    "escalar_para_humano",
    "registrar_consentimento_rgpd",
]


def format_playbook_block(
    playbook: dict,
    stage_id: str,
    patient_message: str = "",
) -> str:
    """
    Formats the current stage's playbook guidance into a system-prompt block.

    Returns "" when playbook is empty (no-op — backward compatible).

    Detects objections from patient_message using pattern matching and injects
    the relevant response strategy when triggered.
    """
    if not playbook:
        return ""

    stages: list[dict] = playbook.get("stages", [])
    current = next((s for s in stages if s.get("id") == stage_id), None)
    if not current:
        return ""

    label    = current.get("label", stage_id)
    goals    = current.get("goals") or []
    probing  = current.get("probing_questions") or []
    advance  = current.get("advance_when") or []
    blocked  = set(current.get("blocked_tools") or [])
    min_turns = current.get("min_turns", 1)

    available = [t for t in _ALL_AGENT_TOOLS if t not in blocked]

    lines: list[str] = [f"## Guia de Conversa — Stage: {label}"]

    if goals:
        lines.append("**Objetivos neste stage:**")
        lines.extend(f"- {g}" for g in goals)

    if probing:
        lines.append("**Perguntas de sondagem (usa quando natural):**")
        lines.extend(f'- "{q}"' for q in probing)

    if advance:
        lines.append("**Avança para o próximo stage quando:**")
        lines.extend(f"- {a}" for a in advance)

    if min_turns > 1:
        lines.append(f"**Mínimo de turnos neste stage:** {min_turns}")

    if blocked:
        lines.append(
            f"**Ferramentas BLOQUEADAS neste stage:** {', '.join(sorted(blocked))}"
        )
        lines.append(
            "Não ofereças agendamento nem verificação de slots ainda. "
            "Concentra-te nos objetivos acima."
        )
    if available:
        lines.append(f"**Ferramentas disponíveis:** {', '.join(available)}")

    # ── Objection detection ───────────────────────────────────────────────────
    if patient_message:
        msg_lower = patient_message.lower()
        triggered: list[dict] = [
            obj for obj in (playbook.get("objections") or [])
            if any(p in msg_lower for p in (obj.get("patterns") or []))
        ]
        if triggered:
            lines.append("**Objeção detectada — responde com esta estratégia:**")
            for obj in triggered:
                lines.append(f"- **{obj.get('name', '?')}**: {obj.get('strategy', '')}")

    return "\n".join(lines)


def get_blocked_tools(playbook: dict, stage_id: str) -> list[str]:
    """Returns the list of blocked tool names for the given stage."""
    for stage in playbook.get("stages", []):
        if stage.get("id") == stage_id:
            return list(stage.get("blocked_tools") or [])
    return []


# ─── Signal patterns ─────────────────────────────────────────────────────────

_RE_SCHEDULING = re.compile(
    r'\b(horário|horario|agendar|marcar|consulta|disponib|segunda|terça|terca|'
    r'quarta|quinta|sexta|sábado|sabado|semana|data|quando|slot)\b',
    re.IGNORECASE,
)
_RE_PRICING = re.compile(
    r'\b(preço|preco|valor|custo|quanto|orçamento|orcamento|custa|pag[ao]|investimento)\b',
    re.IGNORECASE,
)
_RE_CLOSING = re.compile(
    r'\b(confirm[ao]d[ao]|agendad[ao]|marcad[ao]|reservad[ao]|combinado|obrigad|tchau|adeus)\b',
    re.IGNORECASE,
)
_RE_COMPLAINT = re.compile(
    r'\b(reclamaç|reclamac|problema|insatisf|péssim|pessim|horrível|horrivel|absurdo|inaceitável)\b',
    re.IGNORECASE,
)
_RE_PROCEDURE = re.compile(
    r'\b(botox|preenchimento|limpeza|clareamento|canal|extração|extracao|implante|'
    r'ortopedia|cardiolog|dermatol|pediatr|geral|check.?up|cirurgia|avaliação|avaliacao)\b',
    re.IGNORECASE,
)
_RE_DAY = re.compile(
    r'\b(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo|'
    r'manhã|manha|tarde|amanhã|amanha|semana que vem|próxima semana)\b',
    re.IGNORECASE,
)
_RE_HESITANT = re.compile(
    r'\b(não sei|nao sei|talvez|pensar|dúvida|duvida|preocup|medo|nervos)\b',
    re.IGNORECASE,
)
_RE_URGENT = re.compile(
    r'\b(urgente|urgência|urgencia|dor|emergência|emergencia|hoje|agora|rápido|rapido)\b',
    re.IGNORECASE,
)


# ─── Stage machine ────────────────────────────────────────────────────────────

_STAGE_ORDER = ["opening", "discovery", "qualification", "scheduling", "closing"]


def _can_advance(
    stage: str,
    new_intent: str,
    facts: dict,
    combined: str,
    agent_response: str,
) -> bool:
    """Returns True if the conversation can advance past `stage`."""
    if stage == "opening":
        return new_intent != "other" or bool(_RE_PROCEDURE.search(combined))
    if stage == "discovery":
        return bool(facts.get("procedure_interest"))
    if stage == "qualification":
        return new_intent == "scheduling" or bool(_RE_SCHEDULING.search(agent_response))
    if stage == "scheduling":
        return bool(_RE_CLOSING.search(agent_response))
    return False  # "closing" is terminal


# ─── Stage detection ──────────────────────────────────────────────────────────

def detect_stage_from_response(
    agent_response: str,
    patient_message: str,
    current_snapshot: dict,
) -> dict:
    """
    Derives an updated context_snapshot from the latest turn.

    Analyses both agent response and patient message to detect:
      - Intent (scheduling / pricing / complaint / other)
      - Mood (curious / hesitant / urgent / satisfied / frustrated)
      - New facts (procedure, preferred day, budget mention)
      - Stage transitions (up to 2 advances per turn, so a rich message
        like "quero botox, tem segunda?" can jump opening→qualification)

    Regex-only — no LLM calls.
    """
    snapshot = dict(current_snapshot)
    snapshot["facts_captured"] = dict((current_snapshot.get("facts_captured") or {}))

    current_stage: str = snapshot.get("stage", "opening")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Combine both texts; patient message is the authoritative source for facts/mood
    combined = patient_message + " " + agent_response

    # ── Intent ────────────────────────────────────────────────────────────────
    if _RE_COMPLAINT.search(combined):
        new_intent = "complaint"
    elif _RE_SCHEDULING.search(combined):
        new_intent = "scheduling"
    elif _RE_PRICING.search(combined):
        new_intent = "pricing"
    elif _RE_PROCEDURE.search(combined):
        new_intent = "info"
    else:
        new_intent = snapshot.get("intent", "other")

    if new_intent != snapshot.get("intent"):
        snapshot["intent"] = new_intent
        snapshot["last_intent_at"] = now_iso

    # ── Mood (patient message only) ───────────────────────────────────────────
    if _RE_COMPLAINT.search(patient_message):
        snapshot["mood"] = "frustrated"
    elif _RE_URGENT.search(patient_message):
        snapshot["mood"] = "urgent"
    elif _RE_HESITANT.search(patient_message):
        snapshot["mood"] = "hesitant"
    elif _RE_CLOSING.search(agent_response):
        snapshot["mood"] = "satisfied"

    # ── Fact extraction ───────────────────────────────────────────────────────
    proc_match = _RE_PROCEDURE.search(combined)
    if proc_match and not snapshot["facts_captured"].get("procedure_interest"):
        snapshot["facts_captured"]["procedure_interest"] = proc_match.group(0).lower()

    day_match = _RE_DAY.search(patient_message)
    if day_match and not snapshot["facts_captured"].get("preferred_day"):
        snapshot["facts_captured"]["preferred_day"] = day_match.group(0).lower()

    if _RE_PRICING.search(combined):
        snapshot["facts_captured"]["budget_mentioned"] = True

    # ── Stage transitions (allow up to 2 advances per turn) ──────────────────
    stage = current_stage
    for _ in range(2):
        if _can_advance(stage, new_intent, snapshot["facts_captured"], combined, agent_response):
            idx = _STAGE_ORDER.index(stage)
            if idx + 1 < len(_STAGE_ORDER):
                stage = _STAGE_ORDER[idx + 1]
                # Update next_action as we advance
                _NEXT_ACTION = {
                    "discovery":     "ask_procedure",
                    "qualification": "offer_slots",
                    "scheduling":    "confirm_booking",
                    "closing":       "handoff",
                }
                snapshot["next_action"] = _NEXT_ACTION.get(stage, snapshot.get("next_action"))
            else:
                break
        else:
            break

    new_stage = stage

    # ── Turns counter ─────────────────────────────────────────────────────────
    if new_stage == current_stage:
        snapshot["turns_in_stage"] = snapshot.get("turns_in_stage", 0) + 1
    else:
        snapshot["stage"] = new_stage
        snapshot["turns_in_stage"] = 0

    return snapshot
