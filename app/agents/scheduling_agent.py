"""
SchedulingAgent — specialised agent for booking medical appointments.

Usage
-----
class MySchedulingAgent(SchedulingAgent):
    async def check_availability(self, date: str) -> bool: ...
    async def list_available_slots(self, date: str) -> list[Slot]: ...
    async def create_appointment(self, name: str, iso_datetime: str) -> Appointment: ...

agent = MySchedulingAgent(pais="PT")
reply = await agent.run("Quero marcar uma consulta")
"""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.prompts import get_scheduling_prompt

# ─── Value objects ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Slot:
    datetime: str
    available: bool = True

    @property
    def display(self) -> str:
        from datetime import datetime
        dt = datetime.fromisoformat(self.datetime)
        return dt.strftime("%d/%m/%Y às %H:%M")


@dataclass(frozen=True)
class Appointment:
    id: str
    patient_name: str
    datetime: str
    confirmation_code: str = ""

    @property
    def display(self) -> str:
        from datetime import datetime
        dt = datetime.fromisoformat(self.datetime)
        return (
            f"Consulta confirmada!\n"
            f"• Paciente: {self.patient_name}\n"
            f"• Data: {dt.strftime('%d/%m/%Y às %H:%M')}\n"
            f"• Código: {self.confirmation_code or self.id}"
        )


# ─── Tool definitions ──────────────────────────────────────────────────────────

_TOOLS: list[dict] = [
    {
        "name": "check_availability",
        "description": (
            "Verifica se há horários disponíveis em uma data específica. "
            "Retorna true/false. Use antes de listar slots para evitar chamadas desnecessárias."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Data no formato YYYY-MM-DD."}
            },
            "required": ["date"],
        },
    },
    {
        "name": "list_available_slots",
        "description": (
            "Lista todos os horários disponíveis para agendamento em uma data. "
            "Sempre use esta ferramenta antes de sugerir horários ao paciente — "
            "nunca invente horários."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Data no formato YYYY-MM-DD."}
            },
            "required": ["date"],
        },
    },
    {
        "name": "create_appointment",
        "description": (
            "Cria o agendamento após o paciente confirmar nome e horário. "
            "Só chame esta ferramenta depois de confirmar explicitamente com o paciente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string", "description": "Nome completo do paciente."},
                "iso_datetime": {"type": "string", "description": "Data e hora no formato ISO 8601."},
            },
            "required": ["patient_name", "iso_datetime"],
        },
    },
]


# ─── SchedulingAgent ──────────────────────────────────────────────────────────

class SchedulingAgent(BaseAgent):
    """
    Scheduling agent. Persona and language selected by `pais` at construction time.
    Subclass and implement the three abstract data methods.
    """

    def __init__(self, *, pais: str = "PT", api_key: str | None = None) -> None:
        super().__init__(
            system_prompt=get_scheduling_prompt(pais),
            tools=_TOOLS,
            api_key=api_key,
            max_tokens=1024,
            max_iterations=10,
        )

    async def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        match tool_name:
            case "check_availability":
                result = await self.check_availability(tool_input["date"])
                return "Há horários disponíveis." if result else "Nenhum horário disponível nessa data."

            case "list_available_slots":
                slots = await self.list_available_slots(tool_input["date"])
                if not slots:
                    return "Nenhum horário disponível nessa data."
                lines = [f"- {slot.display} (id: {slot.datetime})" for slot in slots if slot.available]
                return "Horários disponíveis:\n" + "\n".join(lines)

            case "create_appointment":
                appointment = await self.create_appointment(
                    name=tool_input["patient_name"],
                    iso_datetime=tool_input["iso_datetime"],
                )
                return appointment.display

            case _:
                raise ValueError(f"Unknown tool: '{tool_name}'")

    @abstractmethod
    async def check_availability(self, date: str) -> bool: ...

    @abstractmethod
    async def list_available_slots(self, date: str) -> list[Slot]: ...

    @abstractmethod
    async def create_appointment(self, name: str, iso_datetime: str) -> Appointment: ...
