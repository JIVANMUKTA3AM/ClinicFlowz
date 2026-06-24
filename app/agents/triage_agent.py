"""
TriageAgent — initial symptom triage for clinic patients.

Caller pattern
--------------
    agent = TriageAgent(pais="PT")   # or "BR"

    while True:
        reply = await agent.run(user_msg)
        if agent.is_complete:
            result = agent.triage_result
            break
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.prompts import get_triage_prompt

logger = logging.getLogger(__name__)


# ─── Domain types ─────────────────────────────────────────────────────────────

class UrgencyLevel(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


@dataclass(frozen=True)
class TriageResult:
    urgency: UrgencyLevel
    summary: str
    recommended_action: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["urgency"] = self.urgency.value
        return d


# ─── Tool definition ──────────────────────────────────────────────────────────

_TOOLS: list[dict] = [
    {
        "name": "submit_triage_result",
        "description": (
            "Finaliza a triagem após coletar informações suficientes. "
            "Chame esta ferramenta somente quando tiver informação suficiente "
            "para classificar a urgência com segurança. "
            "Informe o encaminhamento ao paciente ANTES de chamar esta ferramenta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "urgency": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH"],
                    "description": "Nível de urgência. Em caso de dúvida, use o nível mais alto.",
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "Resumo claro dos sintomas relatados. "
                        "NÃO inclua diagnósticos — apenas fatos relatados."
                    ),
                },
                "recommended_action": {
                    "type": "string",
                    "description": (
                        "Orientação de encaminhamento específica ao nível de urgência."
                    ),
                },
            },
            "required": ["urgency", "summary", "recommended_action"],
        },
    }
]


# ─── TriageAgent ──────────────────────────────────────────────────────────────

class TriageAgent(BaseAgent):
    """
    Conversational triage agent. Language and persona selected by `pais`.

    State
    -----
    triage_result   Populated once the model calls `submit_triage_result`.
    is_complete     True after `triage_result` is set.
    """

    def __init__(self, *, pais: str = "PT", api_key: str | None = None) -> None:
        super().__init__(
            system_prompt=get_triage_prompt(pais),
            tools=_TOOLS,
            api_key=api_key,
            max_tokens=1024,
            max_iterations=15,
        )
        self._triage_result: TriageResult | None = None

    @property
    def triage_result(self) -> TriageResult | None:
        return self._triage_result

    @property
    def is_complete(self) -> bool:
        return self._triage_result is not None

    def reset_history(self) -> None:
        super().reset_history()
        self._triage_result = None

    async def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        if tool_name != "submit_triage_result":
            raise ValueError(f"Unknown tool: '{tool_name}'")

        urgency_raw = tool_input.get("urgency", "").upper()
        try:
            urgency = UrgencyLevel(urgency_raw)
        except ValueError:
            raise ValueError(f"Invalid urgency level '{urgency_raw}'. Must be LOW, MEDIUM, or HIGH.")

        summary = tool_input.get("summary", "").strip()
        recommended_action = tool_input.get("recommended_action", "").strip()

        if not summary:
            raise ValueError("'summary' must not be empty.")
        if not recommended_action:
            raise ValueError("'recommended_action' must not be empty.")

        self._triage_result = TriageResult(
            urgency=urgency,
            summary=summary,
            recommended_action=recommended_action,
        )

        logger.info("Triage complete — urgency=%s | summary=%s", urgency.value, summary[:80])

        return (
            f"Triagem registrada com sucesso.\n"
            f"Urgência: {urgency.value}\n"
            f"Resumo: {summary}\n"
            f"Encaminhamento: {recommended_action}"
        )
