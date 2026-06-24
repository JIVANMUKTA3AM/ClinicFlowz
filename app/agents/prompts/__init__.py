"""
app/agents/prompts — Locale-aware prompt registry.

Usage:
    from app.agents.prompts import get_whatsapp_prompt, get_triage_prompt, ...

All functions accept pais: str ("PT" | "BR") and return the appropriate
system prompt string. Unknown country codes fall back to "PT".
"""

from __future__ import annotations

from app.agents.prompts import pt_pt, pt_br


def _pick(pais: str):
    return pt_pt if pais.upper() == "PT" else pt_br


def get_whatsapp_prompt(pais: str) -> str:
    return _pick(pais).WHATSAPP_PROMPT


def get_triage_prompt(pais: str) -> str:
    return _pick(pais).TRIAGE_SYSTEM_PROMPT


def get_scheduling_prompt(pais: str) -> str:
    return _pick(pais).SCHEDULING_SYSTEM_PROMPT


def build_retention_prompt(campaign_value: str, pais: str) -> str:
    return _pick(pais).build_retention_prompt(campaign_value)


def build_lembrete_message(nome: str, data_hora_str: str, medico_txt: str, pais: str) -> str:
    return _pick(pais).build_lembrete_message(nome, data_hora_str, medico_txt)
