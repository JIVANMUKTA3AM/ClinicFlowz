# agenda.py
from fastapi import APIRouter, Depends, Query
from datetime import date, timedelta
from app.core.database import get_supabase, get_clinica_id
from supabase import Client

router = APIRouter()

@router.get("/semana")
def agenda_semana(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
    inicio: date = Query(default=None),
    medico_id: str = Query(None)
):
    """Retorna todas as consultas da semana com dados expandidos."""
    if not inicio:
        from datetime import datetime, timezone
        inicio = datetime.now(timezone.utc).date()

    fim = inicio + timedelta(days=6)

    query = db.table("consultas") \
        .select("*, pacientes(nome, telefone), medicos(nome, especialidade), salas(nome)") \
        .eq("clinica_id", clinica_id) \
        .gte("data_hora", f"{inicio}T00:00:00") \
        .lte("data_hora", f"{fim}T23:59:59")

    if medico_id:
        query = query.eq("medico_id", medico_id)

    res = query.order("data_hora").execute()
    return {"inicio": str(inicio), "fim": str(fim), "consultas": res.data}


@router.get("/kpis")
def kpis_clinica(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase)
):
    """KPIs principais para o dashboard do gestor."""
    from datetime import datetime, timezone
    hoje = datetime.now(timezone.utc).date()
    inicio_mes = hoje.replace(day=1)

    # Consultas do mês
    consultas_mes = db.table("consultas") \
        .select("status, valor, pago") \
        .eq("clinica_id", clinica_id) \
        .gte("data_hora", f"{inicio_mes}T00:00:00") \
        .execute().data

    total    = len(consultas_mes)
    faltas   = sum(1 for c in consultas_mes if c["status"] == "falta")
    receita  = sum((c["valor"] or 0) for c in consultas_mes if c["pago"])
    taxa_falta = round((faltas / total * 100), 1) if total > 0 else 0

    # Pacientes novos no mês
    novos = db.table("pacientes") \
        .select("id", count="exact") \
        .eq("clinica_id", clinica_id) \
        .gte("created_at", f"{inicio_mes}T00:00:00") \
        .execute().count or 0

    # Pipeline
    leads = db.table("pipeline") \
        .select("id", count="exact") \
        .eq("clinica_id", clinica_id) \
        .eq("etapa", "lead") \
        .execute().count or 0

    return {
        "mes": str(inicio_mes),
        "consultas_total": total,
        "taxa_falta_pct": taxa_falta,
        "receita_realizada_eur": receita,
        "pacientes_novos": novos,
        "leads_pipeline": leads
    }
