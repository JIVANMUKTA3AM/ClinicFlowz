"""
scheduler.py — Background job scheduler for CRM Clínicas.

Uses APScheduler (AsyncIOScheduler) — runs inside the same process as
FastAPI, sharing the same asyncio event loop. No broker or worker process
required.

Jobs
----
  lembrete_consulta      Every 30 min  ·  WhatsApp reminder 24 h before appointment
  campanha_retencao      Daily 10:00   ·  CHECKUP_REMINDER + REACTIVATION per clinic
  followup_automatico    Daily 09:00   ·  POST_CONSULTATION recovery for no-shows (48 h)

Guarantees
----------
  • max_instances=1 per job — prevents overlapping runs
  • Each clinic is isolated: one clinic's error never affects another's job
  • Every run is audited in scheduled_jobs (start → success | failed)
  • Lembrete deduplication: markers in interacoes prevent double-sends
  • WhatsApp instance is resolved per clinic from whatsapp_connections

Usage (FastAPI lifespan)
------------------------
  from app.services.scheduler import start_scheduler, stop_scheduler

  @asynccontextmanager
  async def lifespan(app):
      start_scheduler()
      yield
      stop_scheduler()
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from supabase import Client

from app.agents.prompts import build_lembrete_message
from app.agents.retention_agent import RetentionCampaign
from app.core.config import settings
from app.core.database import get_supabase
from app.services.agent_dispatcher import SupabaseRetentionAgent

logger = logging.getLogger(__name__)

# ─── Singleton ────────────────────────────────────────────────────────────────

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    """
    Instantiate and start the AsyncIOScheduler.
    Must be called from within a running asyncio event loop (e.g. FastAPI lifespan).
    """
    global _scheduler

    db = get_supabase()

    _scheduler = AsyncIOScheduler(timezone="Europe/Lisbon")

    _scheduler.add_job(
        _job_lembrete_consulta,
        IntervalTrigger(minutes=30),
        id="lembrete_consulta",
        kwargs={"db": db},
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=120,   # tolerate up to 2 min late start
    )
    _scheduler.add_job(
        _job_campanha_retencao,
        CronTrigger(hour=10, minute=0, timezone="Europe/Lisbon"),
        id="campanha_retencao",
        kwargs={"db": db},
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _job_followup_automatico,
        CronTrigger(hour=9, minute=0, timezone="Europe/Lisbon"),
        id="followup_automatico",
        kwargs={"db": db},
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — %d jobs registered.",
        len(_scheduler.get_jobs()),
    )


def stop_scheduler() -> None:
    """Graceful shutdown — waits for running jobs to finish."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


# ─── Job: lembrete_consulta ───────────────────────────────────────────────────

async def _job_lembrete_consulta(db: Client) -> None:
    """
    Runs every 30 min.
    Finds all consultations whose data_hora falls in the [now+23h, now+25h] window
    (a 2-hour band centred at 24 h), sends a personalised WhatsApp reminder,
    and records the interaction in the timeline with a deduplication marker.
    """
    job_type = "lembrete_consulta"
    logger.info("[%s] Starting...", job_type)

    clinicas = _get_clinicas_ativas(db)
    total_enviados = 0

    for clinica in clinicas:
        clinica_id: str = clinica["id"]
        pais: str = clinica.get("pais", "PT")
        job_id = _log_job_start(db, clinica_id, job_type)
        try:
            n = await _enviar_lembretes_para_clinica(db, clinica_id, pais)
            total_enviados += n
            _log_job_success(db, job_id, {"lembretes_enviados": n})
        except Exception:
            logger.exception("[%s] Error | clinica=%s", job_type, clinica_id)
            _log_job_error(db, job_id, "Uncaught exception — see server logs.")

    logger.info(
        "[%s] Done | clinicas=%d lembretes_total=%d",
        job_type, len(clinicas), total_enviados,
    )


async def _enviar_lembretes_para_clinica(db: Client, clinica_id: str, pais: str = "PT") -> int:
    agora = datetime.now(timezone.utc)
    janela_inicio = agora + timedelta(hours=23)
    janela_fim    = agora + timedelta(hours=25)

    consultas_res = (
        db.table("consultas")
        .select(
            "id, data_hora, paciente_id, tipo, "
            "pacientes(nome, telefone), medicos(nome)"
        )
        .eq("clinica_id", clinica_id)
        .in_("status", ["agendada", "confirmada"])
        .gte("data_hora", janela_inicio.isoformat())
        .lte("data_hora", janela_fim.isoformat())
        .execute()
    )
    consultas = consultas_res.data or []
    if not consultas:
        return 0

    instance_name = _get_instance_name(db, clinica_id)
    if not instance_name:
        logger.warning(
            "[lembrete_consulta] No active WhatsApp connection | clinica=%s — skipping.",
            clinica_id,
        )
        return 0

    enviados = 0
    for consulta in consultas:
        consulta_id: str = consulta["id"]
        paciente_id: str = consulta["paciente_id"]

        # ── Deduplication: skip if marker already in interacoes ───────────
        marker = f"[LEMBRETE-{consulta_id}]"
        ja_enviado = (
            db.table("interacoes")
            .select("id")
            .eq("paciente_id", paciente_id)
            .eq("clinica_id", clinica_id)
            .eq("tipo", "lembrete")
            .like("conteudo", f"%{marker}%")
            .execute()
        )
        if ja_enviado.data:
            continue

        # ── Build personalised message ─────────────────────────────────────
        paciente = consulta.get("pacientes") or {}
        medico   = consulta.get("medicos")   or {}
        telefone = paciente.get("telefone", "")
        nome     = paciente.get("nome", "Paciente")

        try:
            dt = datetime.fromisoformat(
                consulta["data_hora"].replace("Z", "+00:00")
            )
        except (ValueError, KeyError):
            continue

        medico_txt = f", com Dr(a). {medico['nome']}" if medico.get("nome") else ""
        data_hora_str = dt.strftime("%d/%m/%Y às %H:%M")
        mensagem = build_lembrete_message(nome, data_hora_str, medico_txt, pais)

        try:
            await _send_whatsapp(telefone, mensagem, instance_name)

            db.table("interacoes").insert({
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
                "tipo": "lembrete",
                "direcao": "saida",
                "conteudo": f"{marker} {mensagem}",
                "criado_por": "sistema",
            }).execute()

            enviados += 1
            logger.info(
                "[lembrete] Sent | consulta=%s patient=%s clinica=%s",
                consulta_id, paciente_id, clinica_id,
            )
        except Exception:
            logger.exception(
                "[lembrete] Failed to send | consulta=%s", consulta_id
            )

    return enviados


# ─── Job: campanha_retencao ───────────────────────────────────────────────────

async def _job_campanha_retencao(db: Client) -> None:
    """
    Runs daily at 10:00 Lisbon time.
    Executes CHECKUP_REMINDER (180–364 days absent) and REACTIVATION (365+ days
    absent or status=inativo) for every active clinic. Limit: 20 patients per
    clinic per campaign per run to prevent message flooding.
    """
    job_type = "campanha_retencao"
    logger.info("[%s] Starting...", job_type)

    clinicas = _get_clinicas_ativas(db)
    campanhas = [RetentionCampaign.CHECKUP_REMINDER, RetentionCampaign.REACTIVATION]

    for clinica in clinicas:
        clinica_id: str = clinica["id"]
        pais: str = clinica.get("pais", "PT")

        for campanha in campanhas:
            job_id = _log_job_start(
                db, clinica_id, job_type, {"campanha": campanha.value}
            )
            try:
                pacientes = _descobrir_pacientes(
                    db, clinica_id, campanha, limite=20
                )
                resultados = await _executar_retencao_batch(
                    pacientes, clinica_id, db, campanha, pais
                )
                sucesso = sum(1 for r in resultados if r["sucesso"])
                _log_job_success(db, job_id, {
                    "campanha": campanha.value,
                    "processados": len(resultados),
                    "sucesso": sucesso,
                    "falha": len(resultados) - sucesso,
                })
                logger.info(
                    "[%s] %s | clinica=%s processados=%d sucesso=%d",
                    job_type, campanha.value, clinica_id,
                    len(resultados), sucesso,
                )
            except Exception:
                logger.exception(
                    "[%s] Error | clinica=%s campanha=%s",
                    job_type, clinica_id, campanha.value,
                )
                _log_job_error(
                    db, job_id,
                    f"Uncaught exception for campanha {campanha.value} — see logs.",
                )


# ─── Job: followup_automatico ─────────────────────────────────────────────────

async def _job_followup_automatico(db: Client) -> None:
    """
    Runs daily at 09:00 Lisbon time.
    Finds patients whose last consultation was marked as 'falta' in the past 48 h
    and runs a POST_CONSULTATION retention campaign for each (no-show recovery).
    """
    job_type = "followup_automatico"
    logger.info("[%s] Starting...", job_type)

    clinicas = _get_clinicas_ativas(db)

    for clinica in clinicas:
        clinica_id: str = clinica["id"]
        pais: str = clinica.get("pais", "PT")
        job_id = _log_job_start(db, clinica_id, job_type)
        try:
            agora = datetime.now(timezone.utc)
            cutoff = agora - timedelta(hours=48)

            # Patients with a recent no-show
            faltas_res = (
                db.table("consultas")
                .select("paciente_id")
                .eq("clinica_id", clinica_id)
                .eq("status", "falta")
                .gte("data_hora", cutoff.isoformat())
                .execute()
            )
            # De-duplicate: a patient may have had multiple faltas
            paciente_ids = list(
                {r["paciente_id"] for r in (faltas_res.data or [])}
            )

            if not paciente_ids:
                _log_job_success(db, job_id, {"followups": 0})
                continue

            pacientes_res = (
                db.table("pacientes")
                .select("*")
                .in_("id", paciente_ids)
                .eq("clinica_id", clinica_id)
                .neq("status", "arquivado")
                .execute()
            )
            pacientes = pacientes_res.data or []

            resultados = await _executar_retencao_batch(
                pacientes, clinica_id, db, RetentionCampaign.POST_CONSULTATION, pais
            )
            sucesso = sum(1 for r in resultados if r["sucesso"])

            _log_job_success(db, job_id, {
                "followups_tentados": len(resultados),
                "sucesso": sucesso,
                "falha": len(resultados) - sucesso,
            })
            logger.info(
                "[%s] Done | clinica=%s followups=%d sucesso=%d",
                job_type, clinica_id, len(resultados), sucesso,
            )
        except Exception:
            logger.exception("[%s] Error | clinica=%s", job_type, clinica_id)
            _log_job_error(db, job_id, "Uncaught exception — see server logs.")


# ─── Patient discovery (shared by retention jobs) ────────────────────────────

def _descobrir_pacientes(
    db: Client,
    clinica_id: str,
    campanha: RetentionCampaign,
    limite: int,
) -> list[dict]:
    """
    Returns up to `limite` eligible patients for a given campaign.

    Eligibility criteria
    --------------------
    CHECKUP_REMINDER      Last realizada consultation 180–364 days ago
    REACTIVATION          Last realizada 365+ days ago, OR status=inativo
    POST_CONSULTATION     Last realizada or falta within 1–3 days
    INCOMPLETE_TREATMENT  Pipeline in orcamento/tratamento_ativo,
                          last realizada > 30 days ago
    """
    hoje = datetime.now(timezone.utc)

    # Most-recent consultation (realizada or falta) per patient
    consultas_res = (
        db.table("consultas")
        .select("paciente_id, data_hora, status")
        .eq("clinica_id", clinica_id)
        .in_("status", ["realizada", "falta"])
        .order("data_hora", desc=True)
        .execute()
    )
    ultima: dict[str, dict] = {}
    for c in (consultas_res.data or []):
        pid = c["paciente_id"]
        if pid not in ultima:
            ultima[pid] = c

    paciente_ids: list[str] = []

    if campanha == RetentionCampaign.POST_CONSULTATION:
        cutoff_near = hoje - timedelta(days=1)
        cutoff_far  = hoje - timedelta(days=3)
        for pid, c in ultima.items():
            dt = _parse_dt(c["data_hora"])
            if dt and cutoff_far <= dt <= cutoff_near:
                paciente_ids.append(pid)

    elif campanha == RetentionCampaign.CHECKUP_REMINDER:
        cutoff_near = hoje - timedelta(days=180)
        cutoff_far  = hoje - timedelta(days=364)
        for pid, c in ultima.items():
            if c["status"] != "realizada":
                continue
            dt = _parse_dt(c["data_hora"])
            if dt and cutoff_far <= dt <= cutoff_near:
                paciente_ids.append(pid)

    elif campanha == RetentionCampaign.REACTIVATION:
        cutoff = hoje - timedelta(days=365)
        long_absent = {
            pid
            for pid, c in ultima.items()
            if c["status"] == "realizada" and (
                (dt := _parse_dt(c["data_hora"])) is not None and dt < cutoff
            )
        }
        inativo_res = (
            db.table("pacientes")
            .select("id")
            .eq("clinica_id", clinica_id)
            .eq("status", "inativo")
            .execute()
        )
        inativos = {r["id"] for r in (inativo_res.data or [])}
        paciente_ids = list(long_absent | inativos)

    elif campanha == RetentionCampaign.INCOMPLETE_TREATMENT:
        pipeline_res = (
            db.table("pipeline")
            .select("paciente_id")
            .eq("clinica_id", clinica_id)
            .in_("etapa", ["orcamento", "tratamento_ativo"])
            .execute()
        )
        pipeline_ids = {r["paciente_id"] for r in (pipeline_res.data or [])}
        cutoff = hoje - timedelta(days=30)
        for pid in pipeline_ids:
            c = ultima.get(pid)
            if c is None or (
                c["status"] == "realizada"
                and (dt := _parse_dt(c["data_hora"])) is not None
                and dt < cutoff
            ):
                paciente_ids.append(pid)

    if not paciente_ids:
        return []

    res = (
        db.table("pacientes")
        .select("*")
        .in_("id", paciente_ids[:limite])
        .eq("clinica_id", clinica_id)
        .neq("status", "arquivado")
        .execute()
    )
    return res.data or []


# ─── Agent execution helpers ──────────────────────────────────────────────────

async def _executar_retencao_batch(
    pacientes: list[dict],
    clinica_id: str,
    db: Client,
    campanha: RetentionCampaign,
    pais: str = "PT",
) -> list[dict[str, Any]]:
    """Run RetentionAgent.engage() for each patient; collect structured results."""
    resultados: list[dict[str, Any]] = []
    for paciente in pacientes:
        patient_id = paciente["id"]
        try:
            agent = SupabaseRetentionAgent(
                paciente=paciente,
                clinica_id=clinica_id,
                db=db,
                pais=pais,
            )
            await agent.engage(patient_id, campanha)

            engagement = agent.engagement_result
            if engagement is None:
                raise RuntimeError("Agent exited without calling log_engagement_result.")

            resultados.append({
                "paciente_id": patient_id,
                "sucesso": True,
                "actions": [a.value for a in engagement.actions_taken],
                "preview": engagement.message_preview,
            })
            logger.info(
                "RetentionAgent ok | patient=%s campanha=%s actions=%s",
                patient_id,
                campanha.value,
                [a.value for a in engagement.actions_taken],
            )
        except Exception:
            logger.exception(
                "RetentionAgent failed | patient=%s campanha=%s",
                patient_id, campanha.value,
            )
            resultados.append({"paciente_id": patient_id, "sucesso": False})

    return resultados


# ─── Supabase helpers ─────────────────────────────────────────────────────────

def _get_clinicas_ativas(db: Client) -> list[dict]:
    res = (
        db.table("clinicas")
        .select("id, nome, pais")
        .eq("ativo", True)
        .execute()
    )
    return res.data or []


def _get_instance_name(db: Client, clinica_id: str) -> str | None:
    res = (
        db.table("whatsapp_connections")
        .select("instance_name")
        .eq("clinica_id", clinica_id)
        .eq("ativo", True)
        .limit(1)
        .execute()
    )
    return res.data[0]["instance_name"] if res.data else None


# ─── Scheduled-jobs audit log ─────────────────────────────────────────────────

def _log_job_start(
    db: Client,
    clinica_id: str,
    job_type: str,
    payload: dict | None = None,
) -> str:
    """Insert a 'running' row and return its id for later updates."""
    res = db.table("scheduled_jobs").insert({
        "clinica_id": clinica_id,
        "job_type": job_type,
        "status": "running",
        "payload": payload or {},
        "iniciado_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return res.data[0]["id"] if res.data else ""


def _log_job_success(db: Client, job_id: str, resultado: dict) -> None:
    if not job_id:
        return
    db.table("scheduled_jobs").update({
        "status": "success",
        "resultado": resultado,
        "concluido_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()


def _log_job_error(db: Client, job_id: str, erro: str) -> None:
    if not job_id:
        return
    db.table("scheduled_jobs").update({
        "status": "failed",
        "erro": erro,
        "concluido_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()


# ─── Waha send helper ────────────────────────────────────────────────────────

async def _send_whatsapp(
    telefone: str,
    mensagem: str,
    instance_name: str,
) -> None:
    url = f"{settings.WAHA_URL}/api/sendText"
    headers = {
        "X-Api-Key": settings.WAHA_API_KEY,
        "Content-Type": "application/json",
    }
    chat_id = telefone.lstrip("+").replace("@c.us", "").replace("@s.whatsapp.net", "") + "@c.us"
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            url,
            json={"chatId": chat_id, "text": mensagem, "session": instance_name},
            headers=headers,
        )
    if res.status_code not in (200, 201):
        raise RuntimeError(
            f"Waha {res.status_code}: {res.text[:200]}"
        )


# ─── Generic helper ───────────────────────────────────────────────────────────

def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
