"""
RetentionAgent — proactive patient follow-up and re-engagement.

Caller pattern
--------------
    agent = MyRetentionAgent(pais="BR")
    reply = await agent.engage("patient-uuid", RetentionCampaign.POST_CONSULTATION)
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ─── Domain types ──────────────────────────────────────────────────────────────

class RetentionCampaign(str, Enum):
    POST_CONSULTATION    = "POST_CONSULTATION"
    CHECKUP_REMINDER     = "CHECKUP_REMINDER"
    REACTIVATION         = "REACTIVATION"
    INCOMPLETE_TREATMENT = "INCOMPLETE_TREATMENT"


@dataclass
class PatientHistory:
    patient_id: str
    name: str
    last_visit_date: str | None
    last_visit_type: str | None
    days_since_last_visit: int | None
    pending_treatments: list[str] = field(default_factory=list)
    total_visits: int = 0
    preferred_channel: str = "whatsapp"
    notes: str = ""


@dataclass
class MessageReceipt:
    message_id: str
    patient_id: str
    channel: str
    preview: str
    sent_at: str


@dataclass
class FollowupRecord:
    record_id: str
    patient_id: str
    reason: str
    suggested_date: str | None = None


class EngagementAction(str, Enum):
    MESSAGE_SENT      = "message_sent"
    FOLLOWUP_CREATED  = "followup_suggested"
    NO_ACTION_NEEDED  = "no_action_needed"


@dataclass
class EngagementResult:
    patient_id: str
    campaign: RetentionCampaign
    actions_taken: list[EngagementAction]
    message_preview: str
    summary: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["campaign"] = self.campaign.value
        d["actions_taken"] = [a.value for a in self.actions_taken]
        return d


# ─── Tool definitions ──────────────────────────────────────────────────────────

def _build_tools(patient_id: str) -> list[dict]:
    return [
        {
            "name": "get_patient_history",
            "description": (
                f"Busca o histórico completo do paciente {patient_id}: "
                "última consulta, tratamentos pendentes, preferências e notas. "
                "Chame isto PRIMEIRO, antes de redigir qualquer mensagem."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"patient_id": {"type": "string", "description": "UUID do paciente."}},
                "required": ["patient_id"],
            },
        },
        {
            "name": "send_message",
            "description": (
                "Envia a mensagem de retenção ao paciente pelo canal preferido. "
                "Chame apenas UMA vez por sessão. Nunca envie mensagens genéricas."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "UUID do paciente."},
                    "message": {
                        "type": "string",
                        "description": "Texto completo da mensagem (máx. 400 caracteres).",
                    },
                },
                "required": ["patient_id", "message"],
            },
        },
        {
            "name": "suggest_followup",
            "description": (
                "Registra no CRM uma sugestão de consulta de acompanhamento. "
                "Use apenas quando há necessidade clínica real."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "reason": {"type": "string", "description": "Motivo clínico objetivo."},
                    "suggested_date": {"type": "string", "description": "YYYY-MM-DD (opcional)."},
                },
                "required": ["patient_id", "reason"],
            },
        },
        {
            "name": "log_engagement_result",
            "description": (
                "Finaliza e registra o resultado desta sessão. OBRIGATÓRIO — sempre ao final."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "actions_taken": {
                        "type": "array",
                        "items": {"type": "string", "enum": [a.value for a in EngagementAction]},
                        "description": "Lista de ações realizadas.",
                    },
                    "message_preview": {"type": "string", "description": "Primeiros 120 chars da mensagem."},
                    "summary": {"type": "string", "description": "Resumo objetivo da sessão."},
                },
                "required": ["patient_id", "actions_taken", "message_preview", "summary"],
            },
        },
    ]


# ─── RetentionAgent ────────────────────────────────────────────────────────────

class RetentionAgent(BaseAgent):
    """
    Proactive retention agent. Language and persona selected by `pais`.
    Abstract — subclass and implement the three data methods.
    """

    def __init__(self, *, pais: str = "PT", api_key: str | None = None) -> None:
        super().__init__(
            system_prompt="",  # rebuilt per-campaign in engage()
            tools=[],
            api_key=api_key,
            max_tokens=1024,
            max_iterations=8,
        )
        self._pais = pais
        self._current_campaign: RetentionCampaign | None = None
        self._engagement_result: EngagementResult | None = None

    @property
    def engagement_result(self) -> EngagementResult | None:
        return self._engagement_result

    @property
    def is_complete(self) -> bool:
        return self._engagement_result is not None

    async def engage(self, patient_id: str, campaign: RetentionCampaign) -> str:
        from app.agents.prompts import build_retention_prompt
        self.reset_history()
        self.system_prompt = build_retention_prompt(campaign.value, self._pais)
        self.tools = _build_tools(patient_id)
        self._current_campaign = campaign

        initial_prompt = (
            f"Inicie o atendimento de retenção para o paciente {patient_id}. "
            f"Campanha ativa: {campaign.value}. "
            f"Siga o fluxo obrigatório: busque o histórico, personalize a mensagem, "
            f"envie, registre o resultado."
        )
        return await self.run(initial_prompt)

    def reset_history(self) -> None:
        super().reset_history()
        self._current_campaign = None
        self._engagement_result = None

    async def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        match tool_name:
            case "get_patient_history":
                history = await self.fetch_patient_history(tool_input["patient_id"])
                return _format_history(history)

            case "send_message":
                receipt = await self.dispatch_message(
                    patient_id=tool_input["patient_id"],
                    message=tool_input["message"],
                )
                logger.info("Message sent to patient %s via %s", receipt.patient_id, receipt.channel)
                return (
                    f"Mensagem enviada via {receipt.channel} às {receipt.sent_at}.\n"
                    f"ID: {receipt.message_id}\n"
                    f"Preview: {receipt.preview}"
                )

            case "suggest_followup":
                record = await self.schedule_followup(
                    patient_id=tool_input["patient_id"],
                    reason=tool_input["reason"],
                    suggested_date=tool_input.get("suggested_date"),
                )
                logger.info("Follow-up suggested for patient %s — %s", record.patient_id, record.reason)
                return (
                    f"Sugestão de acompanhamento registrada (ID: {record.record_id}).\n"
                    f"Motivo: {record.reason}"
                    + (f"\nData sugerida: {record.suggested_date}" if record.suggested_date else "")
                )

            case "log_engagement_result":
                return self._handle_log_engagement(tool_input)

            case _:
                raise ValueError(f"Unknown tool: '{tool_name}'")

    @abstractmethod
    async def fetch_patient_history(self, patient_id: str) -> PatientHistory: ...

    @abstractmethod
    async def dispatch_message(self, patient_id: str, message: str) -> MessageReceipt: ...

    @abstractmethod
    async def schedule_followup(
        self, patient_id: str, reason: str, suggested_date: str | None = None
    ) -> FollowupRecord: ...

    def _handle_log_engagement(self, tool_input: dict) -> str:
        raw_actions = tool_input.get("actions_taken", [])
        actions: list[EngagementAction] = []
        for raw in raw_actions:
            try:
                actions.append(EngagementAction(raw))
            except ValueError:
                logger.warning("Unknown action value '%s' — skipping.", raw)

        if not actions:
            actions = [EngagementAction.NO_ACTION_NEEDED]

        self._engagement_result = EngagementResult(
            patient_id=tool_input["patient_id"],
            campaign=self._current_campaign or RetentionCampaign.POST_CONSULTATION,
            actions_taken=actions,
            message_preview=tool_input.get("message_preview", "")[:120],
            summary=tool_input.get("summary", "").strip(),
        )
        logger.info(
            "Engagement logged — patient=%s campaign=%s actions=%s",
            self._engagement_result.patient_id,
            self._engagement_result.campaign.value,
            [a.value for a in actions],
        )
        return "Resultado registrado com sucesso."


# ─── Formatting helper ─────────────────────────────────────────────────────────

def _format_history(h: PatientHistory) -> str:
    lines = [
        f"Nome: {h.name}",
        f"Última consulta: {h.last_visit_date or 'Sem registro'}"
        + (f" ({h.last_visit_type})" if h.last_visit_type else ""),
        f"Dias desde a última visita: {h.days_since_last_visit if h.days_since_last_visit is not None else 'Desconhecido'}",
        f"Total de consultas: {h.total_visits}",
        f"Canal preferido: {h.preferred_channel}",
    ]
    if h.pending_treatments:
        lines.append(f"Tratamentos pendentes: {', '.join(h.pending_treatments)}")
    if h.notes:
        lines.append(f"Notas: {h.notes}")
    return "\n".join(lines)
