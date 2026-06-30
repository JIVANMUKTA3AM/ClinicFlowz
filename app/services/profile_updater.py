"""
profile_updater.py — Persistent ai_profile updater using Claude Haiku.

Called at conversation end (two triggers):
  1. stage reaches "closing" (patient confirmed booking / said goodbye)
  2. new message arrives after 30+ min of silence (implicit conversation end)

Uses claude-haiku-4-5 for cost efficiency — runs once per conversation,
never per turn.  Always called via asyncio.create_task() so it never
blocks the main message flow.

The ai_profile lives on pacientes.ai_profile (permanent, cross-conversation).
The context_snapshot lives on wa_conversations (resets each conversation).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import anthropic
from supabase import Client

from app.core.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 600
_HISTORY_LIMIT = 25

_SCHEMA = """{
  "preferences": {
    "preferred_procedures": ["lista de procedimentos mencionados"],
    "preferred_days": ["lista de dias preferidos"],
    "preferred_time": "manhã | tarde | indiferente"
  },
  "history_summary": "resumo de 1-2 frases sobre histórico e personalidade",
  "last_objection": "última objeção mencionada, ou null",
  "communication_style": "formal | casual | emoji_heavy",
  "total_consultations": 0,
  "last_seen": "ISO 8601 timestamp"
}"""

_SYSTEM = """És um assistente especializado em actualizar perfis de pacientes para clínicas médicas.
Analisa a conversa fornecida e actualiza o ai_profile do paciente.

Regras estritas:
- Mantém dados anteriores se a conversa não fornecer informação nova ou contraditória.
- history_summary: acumula — reflecte o histórico total, não só esta conversa.
- communication_style: formal (usa "você" muito formal), casual (coloquial normal), emoji_heavy (muitos emojis).
- total_consultations: incrementa se a conversa resultou num agendamento confirmado.
- Se um campo não tiver informação nova, copia o valor anterior sem alterações.
- Retorna APENAS JSON puro válido. Sem markdown, sem texto extra."""


async def update_profile(
    db: Client,
    clinica_id: str,
    paciente_id: str,
    nome: str = "Paciente",
) -> None:
    """
    Public entry point — silently swallows all errors.
    Always call via asyncio.create_task() to avoid blocking the turn.
    """
    try:
        await _run(db, clinica_id, paciente_id, nome)
    except Exception:
        logger.exception(
            "profile_updater: unhandled error | clinica=%s paciente=%s",
            clinica_id, paciente_id,
        )


# ─── Internal ─────────────────────────────────────────────────────────────────

async def _run(
    db: Client,
    clinica_id: str,
    paciente_id: str,
    nome: str,
) -> None:
    # ── 1. Load current ai_profile ────────────────────────────────────────────
    pac_res = (
        db.table("pacientes")
        .select("ai_profile, nome")
        .eq("id", paciente_id)
        .eq("clinica_id", clinica_id)
        .limit(1)
        .execute()
    )
    if not pac_res.data:
        logger.warning("profile_updater: patient not found | %s", paciente_id)
        return

    row = pac_res.data[0]
    nome = row.get("nome") or nome
    current_profile: dict = row.get("ai_profile") or {}

    # ── 2. Fetch recent conversation history ──────────────────────────────────
    hist_res = (
        db.table("interacoes")
        .select("tipo, direcao, conteudo, created_at")
        .eq("paciente_id", paciente_id)
        .eq("clinica_id", clinica_id)
        .order("created_at", desc=True)
        .limit(_HISTORY_LIMIT)
        .execute()
    )
    interacoes = list(reversed(hist_res.data or []))

    if not interacoes:
        logger.debug("profile_updater: no history for %s — skipping", paciente_id)
        return

    history_text = _format_history(interacoes)
    current_json = json.dumps(current_profile, ensure_ascii=False, indent=2)
    now_iso = datetime.now(timezone.utc).isoformat()

    user_msg = (
        f"PACIENTE: {nome}\n"
        f"DATA: {now_iso}\n\n"
        f"AI_PROFILE ACTUAL:\n{current_json}\n\n"
        f"SCHEMA DE SAÍDA (retorna exactamente neste formato):\n{_SCHEMA}\n\n"
        f"CONVERSA ({len(interacoes)} mensagens):\n{history_text}\n\n"
        "Retorna o ai_profile actualizado como JSON puro."
    )

    # ── 3. Call Haiku ─────────────────────────────────────────────────────────
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = (response.content[0].text if response.content else "").strip()
    if not raw:
        logger.warning("profile_updater: empty Haiku response | %s", paciente_id)
        return

    # ── 4. Parse JSON (handle accidental markdown wrapping) ───────────────────
    new_profile = _parse_json(raw, paciente_id)
    if new_profile is None:
        return

    new_profile["last_seen"] = now_iso  # always stamp the update time

    # ── 5. Persist ────────────────────────────────────────────────────────────
    db.table("pacientes").update(
        {"ai_profile": new_profile}
    ).eq("id", paciente_id).eq("clinica_id", clinica_id).execute()

    logger.info(
        "profile_updater: updated | patient=%s style=%s summary=%.80s",
        paciente_id,
        new_profile.get("communication_style", "?"),
        new_profile.get("history_summary", ""),
    )


def _parse_json(raw: str, paciente_id: str) -> dict | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences if present
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    logger.error(
        "profile_updater: unparseable JSON | patient=%s | raw=%.300s",
        paciente_id, raw,
    )
    return None


def _format_history(interacoes: list[dict]) -> str:
    lines = []
    for i in interacoes:
        arrow = "→ AGENTE" if i.get("direcao") == "saida" else "← PACIENTE"
        ts = (i.get("created_at") or "")[:16]
        conteudo = (i.get("conteudo") or "")[:200]
        lines.append(f"[{ts}] {arrow}: {conteudo}")
    return "\n".join(lines)
