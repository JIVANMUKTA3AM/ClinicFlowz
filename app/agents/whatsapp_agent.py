from datetime import datetime, timezone, date as date_type
from typing import Any

from supabase import Client

from app.agents.base_agent import BaseAgent
from app.agents.prompts import get_whatsapp_prompt
from app.core.config import settings

# ─── Helpers ──────────────────────────────────────────────────────────────────

_DIA_SEMANA = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sab", 6: "dom"}

_TOOLS = [
    {
        "name": "buscar_medicos",
        "description": (
            "Lista os médicos disponíveis na clínica. "
            "Use para mostrar opções ao paciente ou encontrar um médico por especialidade."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "especialidade": {
                    "type": "string",
                    "description": "Filtrar por especialidade (opcional)."
                }
            },
            "required": []
        }
    },
    {
        "name": "verificar_slots",
        "description": (
            "Verifica os horários disponíveis de um médico numa data específica."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "medico_id": {"type": "string", "description": "UUID do médico"},
                "data": {"type": "string", "description": "Data no formato YYYY-MM-DD"}
            },
            "required": ["medico_id", "data"]
        }
    },
    {
        "name": "agendar_consulta",
        "description": "Agenda uma consulta para o paciente atual com o médico e horário escolhidos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "medico_id": {"type": "string", "description": "UUID do médico"},
                "data_hora": {"type": "string", "description": "ISO 8601, ex: 2025-06-15T09:30:00"},
                "tipo": {
                    "type": "string",
                    "enum": ["primeira_vez", "retorno", "urgencia", "avaliacao"],
                    "description": "Tipo de consulta"
                },
                "observacoes": {"type": "string", "description": "Notas adicionais (opcional)"}
            },
            "required": ["medico_id", "data_hora", "tipo"]
        }
    },
    {
        "name": "cancelar_consulta",
        "description": "Cancela uma consulta agendada ou confirmada do paciente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "consulta_id": {"type": "string", "description": "UUID da consulta a cancelar"}
            },
            "required": ["consulta_id"]
        }
    },
    {
        "name": "escalar_para_humano",
        "description": (
            "Sinaliza que o caso precisa de atenção humana urgente. "
            "Use para urgências clínicas, reclamações, ou situações que não consegue resolver."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {"type": "string", "description": "Motivo que justifica escalar para um humano"}
            },
            "required": ["motivo"]
        }
    },
    {
        "name": "registrar_consentimento_rgpd",
        "description": (
            "Regista o consentimento de privacidade do paciente (RGPD/LGPD). "
            "Use imediatamente após o paciente aceitar verbalmente o tratamento de dados."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# ─── Agent ────────────────────────────────────────────────────────────────────

class WhatsAppAgent(BaseAgent):
    """WhatsApp agent. Persona and language selected by `pais` at construction time."""

    def __init__(self, paciente: dict, clinica_id: str, db: Client, pais: str = "PT") -> None:
        super().__init__(
            system_prompt=get_whatsapp_prompt(pais),
            tools=_TOOLS,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=2048,
        )
        self._paciente = paciente
        self._clinica_id = clinica_id
        self._db = db

    async def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        dispatch = {
            "buscar_medicos":              self._buscar_medicos,
            "verificar_slots":             self._verificar_slots,
            "agendar_consulta":            self._agendar_consulta,
            "cancelar_consulta":           self._cancelar_consulta,
            "escalar_para_humano":         self._escalar_para_humano,
            "registrar_consentimento_rgpd": self._registrar_consentimento_privacidade,
        }
        handler = dispatch.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool: '{tool_name}'")
        return handler(tool_input)

    # ─── Tool handlers ────────────────────────────────────────────────────────

    def _buscar_medicos(self, args: dict) -> str:
        query = (
            self._db.table("medicos")
            .select("id, nome, especialidade, horarios_disponiveis")
            .eq("clinica_id", self._clinica_id)
            .eq("ativo", True)
        )
        especialidade = args.get("especialidade", "").strip()
        if especialidade:
            query = query.ilike("especialidade", f"%{especialidade}%")

        res = query.order("nome").execute()
        if not res.data:
            return "Nenhum médico encontrado."

        linhas = []
        for m in res.data:
            dias = list((m.get("horarios_disponiveis") or {}).keys())
            linhas.append(
                f"- {m['nome']} ({m['especialidade']}) | ID: {m['id']} | Dias: {', '.join(dias) or 'N/D'}"
            )
        return "\n".join(linhas)

    def _verificar_slots(self, args: dict) -> str:
        medico_id = args["medico_id"]
        data_str = args["data"]

        try:
            data = date_type.fromisoformat(data_str)
        except ValueError:
            return f"Data inválida: '{data_str}'. Use o formato YYYY-MM-DD."

        res = (
            self._db.table("medicos")
            .select("nome, horarios_disponiveis")
            .eq("id", medico_id)
            .eq("clinica_id", self._clinica_id)
            .single()
            .execute()
        )
        if not res.data:
            return "Médico não encontrado."

        medico = res.data
        horarios = medico.get("horarios_disponiveis") or {}
        dia_key = _DIA_SEMANA.get(data.weekday(), "")
        slots_dia = horarios.get(dia_key, [])

        if not slots_dia:
            return (
                f"O Dr(a). {medico['nome']} não tem horário disponível em "
                f"{data.strftime('%A')}, {data_str}."
            )

        ocupadas_res = (
            self._db.table("consultas")
            .select("data_hora")
            .eq("medico_id", medico_id)
            .gte("data_hora", f"{data_str}T00:00:00")
            .lte("data_hora", f"{data_str}T23:59:59")
            .in_("status", ["agendada", "confirmada"])
            .execute()
        )
        horas_ocupadas = {r["data_hora"][11:16] for r in (ocupadas_res.data or [])}
        slots_livres = [s for s in slots_dia if s[:5] not in horas_ocupadas]

        if not slots_livres:
            return f"Sem horários disponíveis para {data_str} com o Dr(a). {medico['nome']}."

        return (
            f"Horários disponíveis para Dr(a). {medico['nome']} em {data_str}:\n"
            + ", ".join(slots_livres)
        )

    def _agendar_consulta(self, args: dict) -> str:
        medico_id = args["medico_id"]
        data_hora_str = args["data_hora"]
        tipo = args.get("tipo", "primeira_vez")
        observacoes = args.get("observacoes")

        try:
            dt = datetime.fromisoformat(data_hora_str)
        except ValueError:
            return f"Data/hora inválida: '{data_hora_str}'."

        data_str = dt.date().isoformat()
        hora_str = dt.strftime("%H:%M")

        conflito = (
            self._db.table("consultas")
            .select("id")
            .eq("medico_id", medico_id)
            .gte("data_hora", f"{data_str}T{hora_str}:00")
            .lte("data_hora", f"{data_str}T{hora_str}:59")
            .in_("status", ["agendada", "confirmada"])
            .execute()
        )
        if conflito.data:
            return f"Esse horário ({hora_str}) já está ocupado. Por favor escolha outro."

        nova = {
            "clinica_id": self._clinica_id,
            "paciente_id": self._paciente["id"],
            "medico_id": medico_id,
            "data_hora": dt.isoformat(),
            "tipo": tipo,
            "status": "agendada",
            "duracao_min": 30,
        }
        if observacoes:
            nova["observacoes"] = observacoes

        res = self._db.table("consultas").insert(nova).execute()
        if not res.data:
            return "Erro ao criar consulta. Por favor tente novamente."

        consulta = res.data[0]

        self._db.table("interacoes").insert({
            "clinica_id": self._clinica_id,
            "paciente_id": self._paciente["id"],
            "tipo": "consulta",
            "conteudo": f"Consulta agendada via WhatsApp para {dt.strftime('%d/%m/%Y às %H:%M')}",
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

        return (
            f"Consulta agendada com sucesso! "
            f"ID: {consulta['id']} | "
            f"Data: {dt.strftime('%d/%m/%Y às %H:%M')} | "
            f"Tipo: {tipo}"
        )

    def _cancelar_consulta(self, args: dict) -> str:
        consulta_id = args["consulta_id"]

        res = (
            self._db.table("consultas")
            .update({"status": "cancelada"})
            .eq("id", consulta_id)
            .eq("clinica_id", self._clinica_id)
            .in_("status", ["agendada", "confirmada"])
            .execute()
        )
        if not res.data:
            return "Consulta não encontrada ou já cancelada/realizada."

        self._db.table("interacoes").insert({
            "clinica_id": self._clinica_id,
            "paciente_id": res.data[0]["paciente_id"],
            "tipo": "consulta",
            "conteudo": "Consulta cancelada via WhatsApp pelo paciente",
            "criado_por": "agente_ia",
        }).execute()

        return f"Consulta cancelada com sucesso (ID: {consulta_id})."

    def _escalar_para_humano(self, args: dict) -> str:
        motivo = args.get("motivo", "Sem motivo especificado")

        tags = list(self._paciente.get("tags") or [])
        if "atencao_humana" not in tags:
            tags.append("atencao_humana")
            self._db.table("pacientes").update({"tags": tags}).eq("id", self._paciente["id"]).execute()
            self._paciente["tags"] = tags

        self._db.table("interacoes").insert({
            "clinica_id": self._clinica_id,
            "paciente_id": self._paciente["id"],
            "tipo": "nota",
            "conteudo": f"[ESCALAÇÃO AGENTE] {motivo}",
            "criado_por": "agente_ia",
        }).execute()

        return f"Caso escalado para a equipa humana. Motivo registado: {motivo}"

    def _registrar_consentimento_privacidade(self, args: dict) -> str:
        del args
        if self._paciente.get("consentimento_privacidade_at"):
            return "Consentimento de privacidade já registado anteriormente."

        agora = datetime.now(timezone.utc).isoformat()
        self._db.table("pacientes").update({"consentimento_privacidade_at": agora}).eq(
            "id", self._paciente["id"]
        ).execute()
        self._paciente["consentimento_privacidade_at"] = agora

        self._db.table("interacoes").insert({
            "clinica_id": self._clinica_id,
            "paciente_id": self._paciente["id"],
            "tipo": "nota",
            "conteudo": "Consentimento de privacidade aceite pelo paciente via WhatsApp",
            "criado_por": "agente_ia",
        }).execute()

        return "Consentimento de privacidade registado com sucesso."


# ─── Helpers de contexto ──────────────────────────────────────────────────────

def _formatar_consultas(consultas: list) -> str:
    if not consultas:
        return "Nenhuma consulta agendada"
    return "\n".join(
        f"- ID: {c['id']} | {c['data_hora'][:16]} | {c['tipo']} "
        f"| Dr(a). {(c.get('medicos') or {}).get('nome', 'N/A')} | {c['status']}"
        for c in consultas
    )


def _formatar_historico(historico: list) -> str:
    if not historico:
        return "Sem histórico"
    return "\n".join(
        f"{h['created_at'][:16]} {'→' if h.get('direcao') == 'saida' else '←'} "
        f"[{h['tipo']}] {h['conteudo'][:100]}"
        for h in historico
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

async def processar_mensagem(
    mensagem: str,
    paciente: dict,
    clinica_id: str,
    db: Client,
    pais: str = "PT",
) -> str:
    historico_res = (
        db.table("interacoes")
        .select("tipo, direcao, conteudo, created_at")
        .eq("paciente_id", paciente["id"])
        .eq("clinica_id", clinica_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    consultas_res = (
        db.table("consultas")
        .select("id, data_hora, status, tipo, medicos(nome)")
        .eq("paciente_id", paciente["id"])
        .gte("data_hora", datetime.now(timezone.utc).isoformat())
        .order("data_hora")
        .limit(3)
        .execute()
    )

    tem_consentimento = paciente.get("consentimento_privacidade_at") is not None

    contexto = f"""=== CONTEXTO DO PACIENTE ===
Nome: {paciente.get('nome', 'Não identificado')}
Telefone: {paciente.get('telefone')}
Status: {paciente.get('status')}
Consentimento privacidade: {'Sim' if tem_consentimento else 'Não dado — peça antes de guardar dados de saúde'}
Tags: {', '.join(paciente.get('tags') or []) or 'Nenhuma'}

=== PRÓXIMAS CONSULTAS ===
{_formatar_consultas(consultas_res.data)}

=== HISTÓRICO RECENTE ===
{_formatar_historico(historico_res.data[::-1])}

=== MENSAGEM DO PACIENTE ===
{mensagem}"""

    agent = WhatsAppAgent(paciente=paciente, clinica_id=clinica_id, db=db, pais=pais)
    return await agent.run(contexto)
