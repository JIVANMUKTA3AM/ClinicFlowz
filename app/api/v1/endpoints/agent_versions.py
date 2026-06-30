"""
agent_versions.py — Versionamento do agente WhatsApp com gate de publicação.

Endpoints
---------
  GET  /api/v1/agent-versions/{agent_id}/readiness
       → Calcula score em tempo real (sem criar versão)

  POST /api/v1/agent-versions/{agent_id}
       → Captura snapshot + calcula readiness → cria versão em staging

  GET  /api/v1/agent-versions/{agent_id}
       → Lista versões (mais recentes primeiro)

  POST /api/v1/agent-versions/{agent_id}/{version_id}/publish
       → Publica versão (exige score ≥ 70 e sem bloqueadores)

  POST /api/v1/agent-versions/{agent_id}/{version_id}/restore
       → Restaura configuração de versão anterior
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.database import get_clinica_id, get_supabase
from app.services.readiness_checker import (
    build_snapshot,
    compute_diff,
    compute_readiness,
)

router = APIRouter()


# ─── Schema ───────────────────────────────────────────────────────────────────

class VersionCreate(BaseModel):
    label: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_agent(db: Client, agent_id: str, clinica_id: str) -> dict:
    res = (
        db.table("wa_agents")
        .select("*")
        .eq("id", agent_id)
        .eq("clinica_id", clinica_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")
    return res.data[0]


def _get_version(db: Client, version_id: str, agent_id: str, clinica_id: str) -> dict:
    res = (
        db.table("wa_agent_versions")
        .select("*")
        .eq("id", version_id)
        .eq("agent_id", agent_id)
        .eq("tenant_id", clinica_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")
    return res.data[0]


def _next_version_number(db: Client, agent_id: str) -> int:
    res = (
        db.table("wa_agent_versions")
        .select("version_number")
        .eq("agent_id", agent_id)
        .order("version_number", desc=True)
        .limit(1)
        .execute()
    )
    return (res.data[0]["version_number"] + 1) if res.data else 1


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{agent_id}/readiness")
def get_readiness(
    agent_id: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """Calcula o readiness score em tempo real sem criar uma versão."""
    agent = _get_agent(db, agent_id, clinica_id)
    return compute_readiness(db, clinica_id, agent)


@router.post("/{agent_id}", status_code=201)
def create_version(
    agent_id: str,
    body: VersionCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """
    Captura o estado actual do agente como uma versão em staging.
    Calcula o readiness score e armazena na versão.
    """
    agent     = _get_agent(db, agent_id, clinica_id)
    readiness = compute_readiness(db, clinica_id, agent)
    snapshot  = build_snapshot(agent, readiness)
    ver_num   = _next_version_number(db, agent_id)

    res = db.table("wa_agent_versions").insert({
        "tenant_id":       clinica_id,
        "agent_id":        agent_id,
        "version_number":  ver_num,
        "label":           body.label,
        "snapshot":        snapshot,
        "readiness_score": readiness["score"],
        "readiness_issues": readiness["blockers"],
        "status":          "staging",
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar versão.")

    return {**res.data[0], "readiness": readiness}


@router.get("/{agent_id}")
def list_versions(
    agent_id: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> list[dict]:
    """
    Lista versões do agente, mais recentes primeiro.
    Enriquece cada versão com diff em relação à versão anterior.
    """
    _get_agent(db, agent_id, clinica_id)   # 404 guard

    res = (
        db.table("wa_agent_versions")
        .select("*")
        .eq("agent_id", agent_id)
        .eq("tenant_id", clinica_id)
        .order("version_number", desc=True)
        .execute()
    )
    versions = res.data or []

    # Attach diff: each version vs the one before it (lower version_number)
    for i, ver in enumerate(versions):
        if i < len(versions) - 1:
            prev = versions[i + 1]
            ver["diff"] = compute_diff(ver["snapshot"], prev["snapshot"])
        else:
            ver["diff"] = ["Primeira versão"]

    return versions


@router.post("/{agent_id}/{version_id}/publish")
def publish_version(
    agent_id: str,
    version_id: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """
    Publica uma versão (define como produção activa).
    Bloqueia se score < 70 ou existirem bloqueadores críticos.
    """
    agent   = _get_agent(db, agent_id, clinica_id)
    version = _get_version(db, version_id, agent_id, clinica_id)

    # Re-compute readiness at publish time (conditions may have changed)
    readiness = compute_readiness(db, clinica_id, agent)

    if not readiness["can_publish"]:
        detail_parts = [f"Score: {readiness['score']}/100 (mínimo 70)"]
        detail_parts.extend(readiness["blockers"])
        raise HTTPException(
            status_code=422,
            detail={"message": "Gate de publicação não passou.", "issues": detail_parts},
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    # Un-publish previous production version
    db.table("wa_agent_versions").update({"status": "staging"}).eq(
        "agent_id", agent_id
    ).eq("status", "production").execute()

    # Publish this version
    db.table("wa_agent_versions").update({
        "status": "production",
        "published_at": now_iso,
    }).eq("id", version_id).execute()

    # Update agent pointer
    db.table("wa_agents").update({
        "published_version_id": version_id,
    }).eq("id", agent_id).eq("clinica_id", clinica_id).execute()

    return {
        "published": True,
        "version_id": version_id,
        "version_number": version["version_number"],
        "readiness_score": readiness["score"],
        "published_at": now_iso,
    }


@router.post("/{agent_id}/{version_id}/restore")
def restore_version(
    agent_id: str,
    version_id: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
) -> dict:
    """
    Restaura a configuração do agente a partir de um snapshot anterior.
    Cria automaticamente uma nova versão com o snapshot restaurado.
    """
    agent   = _get_agent(db, agent_id, clinica_id)
    version = _get_version(db, version_id, agent_id, clinica_id)
    snap    = version["snapshot"]

    # Apply snapshot to wa_agents
    updates: dict = {"published_version_id": version_id}
    if "nome" in snap:
        updates["nome"] = snap["nome"]
    if "agent_playbook" in snap:
        updates["agent_playbook"] = snap["agent_playbook"]

    db.table("wa_agents").update(updates).eq(
        "id", agent_id
    ).eq("clinica_id", clinica_id).execute()

    # Create a new version that documents the restore (audit trail)
    readiness = compute_readiness(db, clinica_id, {**agent, **updates})
    new_snapshot = build_snapshot({**agent, **updates}, readiness)
    new_ver_num  = _next_version_number(db, agent_id)

    new_ver_res = db.table("wa_agent_versions").insert({
        "tenant_id":       clinica_id,
        "agent_id":        agent_id,
        "version_number":  new_ver_num,
        "label":           f"Restauro de v{version['version_number']}",
        "snapshot":        new_snapshot,
        "readiness_score": readiness["score"],
        "readiness_issues": readiness["blockers"],
        "status":          "staging",
    }).execute()

    return {
        "restored": True,
        "from_version": version["version_number"],
        "new_version_number": new_ver_num,
        "new_version_id": new_ver_res.data[0]["id"] if new_ver_res.data else None,
    }
