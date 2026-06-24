"""
financeiro.py — Financial reporting endpoints.

Two reports, both multi-tenant and date-filtered:

  GET /financeiro/resumo
      Revenue breakdown: totals, per-doctor split, and per-period trend.
      One Supabase query (consultas JOIN medicos), all aggregation in Python.

  GET /financeiro/comissoes
      Commission calculation per doctor based on realised + paid consultations.
      Uses medicos.comissao_pct (0–100 %).

Design notes
------------
  • Only status='realizada' consultations are included in revenue figures.
  • receita_total    = sum(valor) for realizada (paid + unpaid)
  • receita_paga     = sum(valor) for realizada AND pago=True
  • receita_pendente = receita_total - receita_paga
  • Commissions are calculated only on receita_paga (can't pay out uncollected revenue).
  • Period grouping is configurable: dia | semana | mes (default mes).
  • A single DB query per endpoint is used; all aggregation runs in Python to
    avoid complex SQL that Supabase SDK doesn't support natively.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from supabase import Client

from app.core.database import get_clinica_id, get_supabase

router = APIRouter()


# ─── Response models ──────────────────────────────────────────────────────────

class ReceitaPorMedico(BaseModel):
    medico_id: str
    medico_nome: str
    especialidade: str
    total_consultas: int
    receita_total: float
    receita_paga: float
    receita_pendente: float
    ticket_medio: float


class ReceitaPorPeriodo(BaseModel):
    periodo: str          # "YYYY-MM-DD" | "YYYY-Www" | "YYYY-MM"
    total_consultas: int
    receita_total: float
    receita_paga: float


class ResumoFinanceiro(BaseModel):
    periodo_inicio: str
    periodo_fim: str
    receita_total: float
    receita_paga: float
    receita_pendente: float
    total_consultas: int
    consultas_pagas: int
    consultas_pendentes: int
    ticket_medio: float           # receita_paga / consultas_pagas (0 if none)
    taxa_inadimplencia_pct: float # receita_pendente / receita_total * 100
    por_medico: list[ReceitaPorMedico]
    por_periodo: list[ReceitaPorPeriodo]


class ComissaoPorMedico(BaseModel):
    medico_id: str
    medico_nome: str
    especialidade: str
    comissao_pct: float
    consultas_realizadas: int
    receita_base: float   # pago=True only
    comissao_valor: float


class ComissoesResponse(BaseModel):
    periodo_inicio: str
    periodo_fim: str
    total_comissoes: float
    comissoes: list[ComissaoPorMedico]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/resumo", response_model=ResumoFinanceiro)
def resumo_financeiro(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    data_inicio: Optional[date] = Query(
        None, description="Início do período (YYYY-MM-DD). Default: 1º dia do mês actual."
    ),
    data_fim: Optional[date] = Query(
        None, description="Fim do período (YYYY-MM-DD). Default: hoje."
    ),
    agrupar_por: Literal["dia", "semana", "mes"] = Query(
        "mes", description="Granularidade da série temporal."
    ),
):
    """
    Financial summary for the authenticated clinic.

    Returns overall revenue figures, a per-doctor breakdown, and a time-series
    trend grouped by day / week / month.
    """
    data_inicio, data_fim = _default_period(data_inicio, data_fim)

    consultas = _fetch_consultas_realizadas(db, clinica_id, data_inicio, data_fim)

    # ── Totals ────────────────────────────────────────────────────────────────
    receita_total     = sum(c["valor"] or 0 for c in consultas)
    receita_paga      = sum(c["valor"] or 0 for c in consultas if c["pago"])
    receita_pendente  = receita_total - receita_paga
    total_consultas   = len(consultas)
    consultas_pagas   = sum(1 for c in consultas if c["pago"])
    consultas_pend    = total_consultas - consultas_pagas

    ticket_medio = round(receita_paga / consultas_pagas, 2) if consultas_pagas else 0.0
    taxa_inad    = round(receita_pendente / receita_total * 100, 1) if receita_total else 0.0

    # ── Per-doctor aggregation ─────────────────────────────────────────────────
    medico_map: dict[str, dict] = {}
    for c in consultas:
        mid = c["medico_id"]
        medico_row = c.get("medicos") or {}
        if mid not in medico_map:
            medico_map[mid] = {
                "medico_id": mid,
                "medico_nome": medico_row.get("nome", "Desconhecido"),
                "especialidade": medico_row.get("especialidade", "—"),
                "total_consultas": 0,
                "receita_total": 0.0,
                "receita_paga": 0.0,
            }
        bucket = medico_map[mid]
        bucket["total_consultas"] += 1
        bucket["receita_total"]   += c["valor"] or 0
        if c["pago"]:
            bucket["receita_paga"] += c["valor"] or 0

    por_medico = [
        ReceitaPorMedico(
            **m,
            receita_pendente=round(m["receita_total"] - m["receita_paga"], 2),
            ticket_medio=round(
                m["receita_paga"] / m["total_consultas"], 2
            ) if m["total_consultas"] else 0.0,
            receita_total=round(m["receita_total"], 2),
            receita_paga=round(m["receita_paga"], 2),
        )
        for m in sorted(medico_map.values(), key=lambda x: x["receita_paga"], reverse=True)
    ]

    # ── Time-series aggregation ────────────────────────────────────────────────
    periodo_map: dict[str, dict] = {}
    for c in consultas:
        try:
            dt = datetime.fromisoformat(c["data_hora"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        key = _periodo_key(dt, agrupar_por)
        if key not in periodo_map:
            periodo_map[key] = {"total_consultas": 0, "receita_total": 0.0, "receita_paga": 0.0}
        p = periodo_map[key]
        p["total_consultas"] += 1
        p["receita_total"]   += c["valor"] or 0
        if c["pago"]:
            p["receita_paga"] += c["valor"] or 0

    por_periodo = [
        ReceitaPorPeriodo(
            periodo=k,
            total_consultas=v["total_consultas"],
            receita_total=round(v["receita_total"], 2),
            receita_paga=round(v["receita_paga"], 2),
        )
        for k, v in sorted(periodo_map.items())
    ]

    return ResumoFinanceiro(
        periodo_inicio=str(data_inicio),
        periodo_fim=str(data_fim),
        receita_total=round(receita_total, 2),
        receita_paga=round(receita_paga, 2),
        receita_pendente=round(receita_pendente, 2),
        total_consultas=total_consultas,
        consultas_pagas=consultas_pagas,
        consultas_pendentes=consultas_pend,
        ticket_medio=ticket_medio,
        taxa_inadimplencia_pct=taxa_inad,
        por_medico=por_medico,
        por_periodo=por_periodo,
    )


@router.get("/comissoes", response_model=ComissoesResponse)
def calcular_comissoes(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    medico_id: Optional[str] = Query(None, description="Filtrar por médico específico."),
):
    """
    Commission report per doctor.

    Commissions are calculated only on **paid** consultations
    (pago=True) using each doctor's comissao_pct stored in medicos.
    Unpaid revenue is excluded to avoid paying out uncollected income.
    """
    data_inicio, data_fim = _default_period(data_inicio, data_fim)

    consultas = _fetch_consultas_realizadas(
        db, clinica_id, data_inicio, data_fim, medico_id=medico_id
    )
    # Commission base = pago only
    pagas = [c for c in consultas if c["pago"]]

    medico_map: dict[str, dict] = {}
    for c in pagas:
        mid = c["medico_id"]
        medico_row = c.get("medicos") or {}
        if mid not in medico_map:
            medico_map[mid] = {
                "medico_id": mid,
                "medico_nome": medico_row.get("nome", "Desconhecido"),
                "especialidade": medico_row.get("especialidade", "—"),
                "comissao_pct": float(medico_row.get("comissao_pct") or 0),
                "consultas_realizadas": 0,
                "receita_base": 0.0,
            }
        bucket = medico_map[mid]
        bucket["consultas_realizadas"] += 1
        bucket["receita_base"]         += c["valor"] or 0

    comissoes = [
        ComissaoPorMedico(
            medico_id=m["medico_id"],
            medico_nome=m["medico_nome"],
            especialidade=m["especialidade"],
            comissao_pct=m["comissao_pct"],
            consultas_realizadas=m["consultas_realizadas"],
            receita_base=round(m["receita_base"], 2),
            comissao_valor=round(m["receita_base"] * m["comissao_pct"] / 100, 2),
        )
        for m in sorted(medico_map.values(), key=lambda x: x["receita_base"], reverse=True)
    ]

    return ComissoesResponse(
        periodo_inicio=str(data_inicio),
        periodo_fim=str(data_fim),
        total_comissoes=round(sum(c.comissao_valor for c in comissoes), 2),
        comissoes=comissoes,
    )


# ─── Shared query ─────────────────────────────────────────────────────────────

def _fetch_consultas_realizadas(
    db: Client,
    clinica_id: str,
    data_inicio: date,
    data_fim: date,
    medico_id: str | None = None,
) -> list[dict]:
    """
    Single optimised query: consultas JOIN medicos filtered by clinic, date range,
    and status='realizada'.

    Returns raw rows; all aggregation is done by the caller in Python.
    """
    query = (
        db.table("consultas")
        .select(
            "id, data_hora, valor, pago, forma_pagamento, medico_id, "
            "medicos(nome, especialidade, comissao_pct)"
        )
        .eq("clinica_id", clinica_id)
        .eq("status", "realizada")
        .gte("data_hora", f"{data_inicio}T00:00:00")
        .lte("data_hora", f"{data_fim}T23:59:59")
    )
    if medico_id:
        query = query.eq("medico_id", medico_id)

    return query.order("data_hora").execute().data or []


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _default_period(
    data_inicio: date | None,
    data_fim: date | None,
) -> tuple[date, date]:
    hoje = datetime.now(timezone.utc).date()
    return (
        data_inicio or hoje.replace(day=1),
        data_fim    or hoje,
    )


def _periodo_key(dt: datetime, agrupar_por: str) -> str:
    if agrupar_por == "dia":
        return dt.strftime("%Y-%m-%d")
    if agrupar_por == "semana":
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return dt.strftime("%Y-%m")   # mes (default)
