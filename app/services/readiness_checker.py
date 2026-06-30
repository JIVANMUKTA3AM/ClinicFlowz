"""
readiness_checker.py — Calcula o readiness score do agente (0-100).

Critérios de pontuação:
  +20  KB com documentos activos
  +20  Playbook de conversa configurado (≥ 3 stages com goals)
  +15  Persona personalizada (nome ≠ padrão)
  +20  Sandbox aprovado nos últimos 7 dias (sem hallucination_flag)
  +15  Instância WhatsApp activa
  +10  Sandbox testado nas últimas 24h

Bloqueadores críticos (impedem publicação mesmo com score ≥ 70):
  - Nenhuma instância WhatsApp activa
  - Nenhum sandbox aprovado nos últimos 7 dias

Publicação exige: score ≥ 70 AND sem bloqueadores.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from supabase import Client

_DEFAULT_AGENT_NAME = "Agente WhatsApp"


def compute_readiness(db: Client, clinica_id: str, agent: dict) -> dict:
    """
    Returns:
        score          int 0-100
        breakdown      list[{criterion, points, earned, note}]
        blockers       list[str]   — must be empty to publish
        can_publish    bool        — score ≥ 70 and no blockers
    """
    score      = 0
    breakdown  = []
    blockers   = []
    now        = datetime.now(timezone.utc)

    # ── +20: KB com documentos activos ────────────────────────────────────
    kb_res = (
        db.table("wa_kb_entities")
        .select("id")
        .eq("tenant_id", clinica_id)
        .eq("active", True)
        .limit(200)
        .execute()
    )
    kb_count = len(kb_res.data or [])
    kb_pts   = 20 if kb_count > 0 else 0
    score   += kb_pts
    breakdown.append({
        "criterion": "Base de Conhecimento populada",
        "points": 20,
        "earned": kb_pts,
        "ok":     kb_pts > 0,
        "note":   f"{kb_count} documento(s) activo(s)" if kb_count else "Nenhum documento na KB — seed ou adiciona via Configurações → Conhecimento",
    })

    # ── +20: Playbook configurado ──────────────────────────────────────────
    playbook = agent.get("agent_playbook") or {}
    stages   = playbook.get("stages", [])
    stages_with_goals = [s for s in stages if s.get("goals")]
    has_playbook = len(stages_with_goals) >= 3
    play_pts = 20 if has_playbook else 0
    score   += play_pts
    breakdown.append({
        "criterion": "Playbook de conversa configurado",
        "points": 20,
        "earned": play_pts,
        "ok":     play_pts > 0,
        "note":   f"{len(stages_with_goals)} stages com goals" if has_playbook else f"Apenas {len(stages_with_goals)}/3 stages com goals — edita o playbook",
    })

    # ── +15: Persona personalizada ────────────────────────────────────────
    nome          = agent.get("nome", _DEFAULT_AGENT_NAME)
    persona_ok    = nome != _DEFAULT_AGENT_NAME and len(nome.strip()) > 3
    persona_pts   = 15 if persona_ok else 0
    score        += persona_pts
    breakdown.append({
        "criterion": "Persona personalizada (nome do agente)",
        "points": 15,
        "earned": persona_pts,
        "ok":     persona_pts > 0,
        "note":   f"Nome: \"{nome}\"" if persona_ok else f"Ainda com nome padrão — altera para algo como \"Sofia\" ou \"Carlos\"",
    })

    # ── +20: Sandbox aprovado nos últimos 7 dias ──────────────────────────
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    eval_res  = (
        db.table("wa_agent_runs")
        .select("id")
        .eq("clinica_id", clinica_id)
        .eq("source", "sandbox")
        .eq("hallucination_flag", False)
        .gte("created_at", cutoff_7d)
        .limit(1)
        .execute()
    )
    eval_count = len(eval_res.data or [])
    eval_pts   = 20 if eval_count > 0 else 0
    score     += eval_pts
    if eval_count == 0:
        blockers.append("Nenhum sandbox aprovado nos últimos 7 dias")
    breakdown.append({
        "criterion": "Sandbox aprovado (sem hallucination)",
        "points": 20,
        "earned": eval_pts,
        "ok":     eval_pts > 0,
        "note":   "Pelo menos 1 teste passou" if eval_count else "Corre um sandbox sem flags de hallucination",
    })

    # ── +15: Instância WhatsApp activa ────────────────────────────────────
    conn_res  = (
        db.table("whatsapp_connections")
        .select("id")
        .eq("clinica_id", clinica_id)
        .eq("ativo", True)
        .limit(1)
        .execute()
    )
    conn_count = len(conn_res.data or [])
    conn_pts   = 15 if conn_count > 0 else 0
    score     += conn_pts
    if conn_count == 0:
        blockers.append("Nenhuma instância WhatsApp activa — conecta em Configurações → WhatsApp")
    breakdown.append({
        "criterion": "Instância WhatsApp activa",
        "points": 15,
        "earned": conn_pts,
        "ok":     conn_pts > 0,
        "note":   f"{conn_count} instância(s) conectada(s)" if conn_count else "Sem instância WhatsApp — impede publicação",
    })

    # ── +10: Sandbox testado nas últimas 24h ──────────────────────────────
    cutoff_24h   = (now - timedelta(hours=24)).isoformat()
    recent_res   = (
        db.table("wa_agent_runs")
        .select("id")
        .eq("clinica_id", clinica_id)
        .eq("source", "sandbox")
        .gte("created_at", cutoff_24h)
        .limit(1)
        .execute()
    )
    recent_count = len(recent_res.data or [])
    recent_pts   = 10 if recent_count > 0 else 0
    score       += recent_pts
    breakdown.append({
        "criterion": "Sandbox testado nas últimas 24h",
        "points": 10,
        "earned": recent_pts,
        "ok":     recent_pts > 0,
        "note":   "Teste recente encontrado" if recent_count else "Nenhum sandbox nas últimas 24h — recomendado antes de publicar",
    })

    return {
        "score":       min(score, 100),
        "breakdown":   breakdown,
        "blockers":    blockers,
        "can_publish": score >= 70 and len(blockers) == 0,
        "kb_count":    kb_count,
        "wa_connected": conn_count > 0,
    }


def build_snapshot(agent: dict, readiness: dict) -> dict:
    """
    Builds the immutable snapshot JSONB that goes into wa_agent_versions.
    """
    return {
        "nome":           agent.get("nome", _DEFAULT_AGENT_NAME),
        "agent_playbook": agent.get("agent_playbook") or {},
        "model":          "claude-opus-4-6",
        "kb_count":       readiness.get("kb_count", 0),
        "wa_connected":   readiness.get("wa_connected", False),
        "readiness_score": readiness.get("score", 0),
        "captured_at":    datetime.now(timezone.utc).isoformat(),
    }


def compute_diff(snap_curr: dict, snap_prev: dict) -> list[str]:
    """Returns a human-readable list of changes between two snapshots."""
    changes: list[str] = []

    if snap_curr.get("nome") != snap_prev.get("nome"):
        changes.append(f"Nome: \"{snap_prev.get('nome')}\" → \"{snap_curr.get('nome')}\"")

    curr_stages = snap_curr.get("agent_playbook", {}).get("stages", [])
    prev_stages = snap_prev.get("agent_playbook", {}).get("stages", [])
    if curr_stages != prev_stages:
        changes.append(f"Playbook actualizado ({len(curr_stages)} stages)")

    curr_obj = snap_curr.get("agent_playbook", {}).get("objections", [])
    prev_obj = snap_prev.get("agent_playbook", {}).get("objections", [])
    if curr_obj != prev_obj:
        changes.append(f"Objeções actualizadas ({len(curr_obj)} entradas)")

    curr_kb = snap_curr.get("kb_count", 0)
    prev_kb = snap_prev.get("kb_count", 0)
    if curr_kb != prev_kb:
        arrow = "↑" if curr_kb > prev_kb else "↓"
        changes.append(f"KB: {prev_kb} → {curr_kb} docs {arrow}")

    if snap_curr.get("wa_connected") != snap_prev.get("wa_connected"):
        state = "conectado" if snap_curr.get("wa_connected") else "desconectado"
        changes.append(f"WhatsApp: agora {state}")

    if not changes:
        changes = ["Sem alterações detectadas"]

    return changes
