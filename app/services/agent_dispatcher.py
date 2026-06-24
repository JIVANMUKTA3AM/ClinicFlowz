"""
agent_dispatcher.py — Intelligent agent dispatch layer.

Fetches the clinic's `pais` at the start of each dispatch and passes it
to every agent so persona and language are always consistent within a clinic.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx
from supabase import Client

from app.agents.retention_agent import (
    FollowupRecord,
    MessageReceipt,
    PatientHistory,
    RetentionAgent,
)
from app.agents.router import AgentType, RouterResult
from app.agents.scheduling_agent import Appointment, Slot, SchedulingAgent
from app.agents.triage_agent import TriageAgent
from app.agents.whatsapp_agent import processar_mensagem
from app.core.config import settings

logger = logging.getLogger(__name__)

_DIA_SEMANA: dict[int, str] = {
    0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sab", 6: "dom"
}


# ─── Concrete SchedulingAgent ─────────────────────────────────────────────────

class SupabaseSchedulingAgent(SchedulingAgent):

    def __init__(self, paciente: dict, clinica_id: str, db: Client, pais: str = "PT") -> None:
        super().__init__(pais=pais, api_key=settings.ANTHROPIC_API_KEY)
        self._paciente = paciente
        self._clinica_id = clinica_id
        self._db = db
        self._slot_medico_map: dict[str, str] = {}

    async def check_availability(self, date: str) -> bool:
        slots = await self.list_available_slots(date)
        return len(slots) > 0

    async def list_available_slots(self, date: str) -> list[Slot]:
        try:
            d = datetime.fromisoformat(date).date()
        except ValueError:
            logger.warning("SchedulingAgent: invalid date '%s'", date)
            return []

        dia_key = _DIA_SEMANA.get(d.weekday(), "")

        medicos_res = (
            self._db.table("medicos")
            .select("id, nome, horarios_disponiveis")
            .eq("clinica_id", self._clinica_id)
            .eq("ativo", True)
            .execute()
        )

        ocupadas_res = (
            self._db.table("consultas")
            .select("medico_id, data_hora")
            .eq("clinica_id", self._clinica_id)
            .gte("data_hora", f"{date}T00:00:00")
            .lte("data_hora", f"{date}T23:59:59")
            .in_("status", ["agendada", "confirmada"])
            .execute()
        )
        ocupadas: set[tuple[str, str]] = {
            (r["medico_id"], r["data_hora"][11:16])
            for r in (ocupadas_res.data or [])
        }

        slots: list[Slot] = []
        self._slot_medico_map.clear()

        for medico in (medicos_res.data or []):
            horarios = medico.get("horarios_disponiveis") or {}
            for hora in horarios.get(dia_key, []):
                hora_hhmm = hora[:5]
                if (medico["id"], hora_hhmm) not in ocupadas:
                    iso = f"{date}T{hora_hhmm}:00"
                    self._slot_medico_map[iso] = medico["id"]
                    slots.append(Slot(datetime=iso))

        return slots

    async def create_appointment(self, name: str, iso_datetime: str) -> Appointment:
        medico_id = self._slot_medico_map.get(iso_datetime)
        if not medico_id:
            raise ValueError(
                f"Slot '{iso_datetime}' não encontrado. "
                "Chame list_available_slots novamente e peça ao paciente para escolher."
            )

        nova: dict = {
            "clinica_id": self._clinica_id,
            "paciente_id": self._paciente["id"],
            "medico_id": medico_id,
            "data_hora": iso_datetime,
            "tipo": "primeira_vez",
            "status": "agendada",
            "duracao_min": 30,
        }
        res = self._db.table("consultas").insert(nova).execute()
        if not res.data:
            raise RuntimeError("Falha ao persistir consulta no Supabase.")

        consulta_id: str = res.data[0]["id"]

        self._db.table("interacoes").insert({
            "clinica_id": self._clinica_id,
            "paciente_id": self._paciente["id"],
            "tipo": "consulta",
            "conteudo": f"Consulta agendada via WhatsApp (SchedulingAgent) para {iso_datetime}",
            "criado_por": "agente_ia",
        }).execute()

        pipeline_res = (
            self._db.table("pipeline")
            .select("id, etapa")
            .eq("paciente_id", self._paciente["id"])
            .eq("clinica_id", self._clinica_id)
            .single()
            .execute()
        )
        if pipeline_res.data and pipeline_res.data["etapa"] == "lead":
            self._db.table("pipeline").update({
                "etapa": "agendou",
                "etapa_updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", pipeline_res.data["id"]).execute()

        logger.info("SchedulingAgent: appointment created | consulta=%s patient=%s", consulta_id, self._paciente["id"])
        return Appointment(id=consulta_id, patient_name=name, datetime=iso_datetime)


# ─── Concrete RetentionAgent ──────────────────────────────────────────────────

class SupabaseRetentionAgent(RetentionAgent):

    def __init__(self, paciente: dict, clinica_id: str, db: Client, pais: str = "PT") -> None:
        super().__init__(pais=pais, api_key=settings.ANTHROPIC_API_KEY)
        self._paciente = paciente
        self._clinica_id = clinica_id
        self._db = db

    async def fetch_patient_history(self, patient_id: str) -> PatientHistory:
        consultas_res = (
            self._db.table("consultas")
            .select("data_hora, tipo, status")
            .eq("paciente_id", patient_id)
            .eq("clinica_id", self._clinica_id)
            .order("data_hora", desc=True)
            .limit(20)
            .execute()
        )
        consultas = consultas_res.data or []

        last_done = next((c for c in consultas if c["status"] == "realizada"), None)
        last_falta = next((c for c in consultas if c["status"] == "falta"), None)
        pending = [c["tipo"] for c in consultas if c["status"] in ("agendada", "confirmada")]

        days_since: int | None = None
        if last_done:
            try:
                dt = datetime.fromisoformat(last_done["data_hora"].replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - dt).days
            except (ValueError, TypeError):
                pass

        interacoes_res = (
            self._db.table("interacoes")
            .select("tipo, direcao, conteudo, created_at, criado_por")
            .eq("paciente_id", patient_id)
            .eq("clinica_id", self._clinica_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        interacoes = interacoes_res.data or []

        pipeline_res = (
            self._db.table("pipeline")
            .select("etapa, etapa_updated_at, valor_estimado, observacoes")
            .eq("paciente_id", patient_id)
            .eq("clinica_id", self._clinica_id)
            .single()
            .execute()
        )
        pipeline = pipeline_res.data or {}

        notes_parts: list[str] = []
        if self._paciente.get("notas"):
            notes_parts.append(f"Notas: {self._paciente['notas']}")
        tags = self._paciente.get("tags") or []
        if tags:
            notes_parts.append(f"Tags: {', '.join(tags)}")
        if pipeline:
            loc = self._get_locale_simbolo()
            notes_parts.append(
                f"Pipeline: {pipeline.get('etapa', 'desconhecido')}"
                + (f" (valor estimado: {pipeline['valor_estimado']}{loc})"
                   if pipeline.get("valor_estimado") else "")
            )
        if last_falta:
            notes_parts.append(f"Última falta: {last_falta['data_hora'][:10]} ({last_falta['tipo']})")
        if interacoes:
            recent = "; ".join(
                f"{i['created_at'][:10]} [{i['tipo']}] {i['conteudo'][:60]}"
                for i in interacoes[:3]
            )
            notes_parts.append(f"Interações recentes: {recent}")

        return PatientHistory(
            patient_id=patient_id,
            name=self._paciente.get("nome", "Paciente"),
            last_visit_date=last_done["data_hora"][:10] if last_done else None,
            last_visit_type=last_done["tipo"] if last_done else None,
            days_since_last_visit=days_since,
            pending_treatments=pending,
            total_visits=sum(1 for c in consultas if c["status"] == "realizada"),
            preferred_channel="whatsapp",
            notes="\n".join(notes_parts),
        )

    def _get_locale_simbolo(self) -> str:
        from app.core.locale import get_locale
        return get_locale(self._pais).simbolo_moeda

    def _resolver_instance_name(self) -> str:
        res = (
            self._db.table("whatsapp_connections")
            .select("instance_name")
            .eq("clinica_id", self._clinica_id)
            .eq("ativo", True)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError(f"Nenhuma conexão WhatsApp activa para clinica_id={self._clinica_id}")
        return res.data[0]["instance_name"]

    async def dispatch_message(self, patient_id: str, message: str) -> MessageReceipt:
        telefone = self._paciente.get("telefone", "")
        instance_name = self._resolver_instance_name()
        url = f"{settings.WAHA_URL}/api/sendText"
        headers = {"X-Api-Key": settings.WAHA_API_KEY, "Content-Type": "application/json"}
        chat_id = telefone.lstrip("+").replace("@c.us", "").replace("@s.whatsapp.net", "") + "@c.us"

        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                url,
                json={"chatId": chat_id, "text": message, "session": instance_name},
                headers=headers,
            )
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Waha error {res.status_code}: {res.text}")

        self._db.table("interacoes").insert({
            "clinica_id": self._clinica_id,
            "paciente_id": patient_id,
            "tipo": "whatsapp",
            "direcao": "saida",
            "conteudo": message,
            "criado_por": "agente_ia",
        }).execute()

        logger.info("RetentionAgent: message dispatched | patient=%s | preview=%.60s", patient_id, message)
        return MessageReceipt(
            message_id=str(uuid.uuid4()),
            patient_id=patient_id,
            channel="whatsapp",
            preview=message[:120],
            sent_at=datetime.now(timezone.utc).isoformat(),
        )

    async def schedule_followup(self, patient_id: str, reason: str, suggested_date: str | None = None) -> FollowupRecord:
        conteudo = f"[FOLLOW-UP] {reason}"
        if suggested_date:
            conteudo += f" — Data sugerida: {suggested_date}"

        res = self._db.table("interacoes").insert({
            "clinica_id": self._clinica_id,
            "paciente_id": patient_id,
            "tipo": "lembrete",
            "conteudo": conteudo,
            "criado_por": "agente_ia",
        }).execute()

        record_id: str = res.data[0]["id"] if res.data else str(uuid.uuid4())
        logger.info("RetentionAgent: follow-up recorded | patient=%s | reason=%.60s", patient_id, reason)
        return FollowupRecord(record_id=record_id, patient_id=patient_id, reason=reason, suggested_date=suggested_date)


# ─── Public dispatch function ─────────────────────────────────────────────────

def _get_clinica_pais(clinica_id: str, db: Client) -> str:
    """Resolve pais from DB for this clinic. Defaults to 'PT' on any error."""
    try:
        res = db.table("clinicas").select("pais").eq("id", clinica_id).single().execute()
        return (res.data or {}).get("pais", "PT")
    except Exception:
        logger.warning("Could not resolve pais for clinica_id=%s — defaulting to PT", clinica_id)
        return "PT"


async def dispatch_agent(
    route: RouterResult,
    texto: str,
    paciente: dict,
    clinica_id: str,
    db: Client,
) -> str:
    patient_id: str = paciente["id"]
    pais = _get_clinica_pais(clinica_id, db)

    logger.info(
        "dispatch_agent | agent=%s confidence=%.0f%% tier=%s pais=%s | patient=%s clinica=%s",
        route.agent_name, route.confidence * 100, route.tier.value, pais, patient_id, clinica_id,
    )

    try:
        if route.agent == AgentType.SCHEDULING:
            agent = SupabaseSchedulingAgent(paciente, clinica_id, db, pais=pais)
            contexto = (
                f"Paciente: {paciente.get('nome', 'Não identificado')} "
                f"(tel: {paciente.get('telefone')})\n\n"
                f"Mensagem: {texto}"
            )
            return await agent.run(contexto)

        if route.agent == AgentType.TRIAGE:
            agent = TriageAgent(pais=pais, api_key=settings.ANTHROPIC_API_KEY)
            resposta = await agent.run(texto)

            if agent.is_complete and agent.triage_result:
                result = agent.triage_result
                db.table("interacoes").insert({
                    "clinica_id": clinica_id,
                    "paciente_id": patient_id,
                    "tipo": "nota",
                    "conteudo": (
                        f"[TRIAGEM] Urgência: {result.urgency.value} | "
                        f"Resumo: {result.summary} | "
                        f"Encaminhamento: {result.recommended_action}"
                    ),
                    "criado_por": "agente_ia",
                }).execute()
                logger.info("dispatch_agent | triage saved | patient=%s urgency=%s", patient_id, result.urgency.value)

            return resposta

        if route.agent == AgentType.RETENTION:
            agent = SupabaseRetentionAgent(paciente, clinica_id, db, pais=pais)
            return await agent.run(texto)

    except Exception:
        logger.exception(
            "dispatch_agent | agent=%s failed | patient=%s — falling back to WhatsAppAgent",
            route.agent_name, patient_id,
        )

    logger.info("dispatch_agent | fallback to WhatsAppAgent | patient=%s", patient_id)
    return await processar_mensagem(mensagem=texto, paciente=paciente, clinica_id=clinica_id, db=db, pais=pais)
