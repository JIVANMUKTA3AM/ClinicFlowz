import asyncio
import logging
from datetime import datetime, timezone, date as date_type
from typing import Any

from supabase import Client

from app.agents.base_agent import BaseAgent
from app.agents.prompts import get_whatsapp_prompt
from app.core.config import settings
from app.services import profile_updater
from app.services.prompt_builder import (
    default_snapshot,
    detect_stage_from_response,
    format_playbook_block,
    format_profile_block,
    format_snapshot_block,
    get_blocked_tools,
)

logger = logging.getLogger(__name__)

_INACTIVITY_MINUTES = 30

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
    },
    {
        "name": "search_kb",
        "description": (
            "Busca na base de conhecimento da clínica. "
            "Use SEMPRE que o paciente perguntar sobre serviços, preços, procedimentos, "
            "FAQ, localização, horários ou qualquer informação da clínica. "
            "Nunca inventes informações — consulta sempre a KB primeiro."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A pergunta ou tema a pesquisar (ex: 'quanto custa botox', 'endereço da clínica')"
                }
            },
            "required": ["query"]
        }
    }
]


# ─── Agent ────────────────────────────────────────────────────────────────────

class WhatsAppAgent(BaseAgent):
    """WhatsApp agent. Persona and language selected by `pais` at construction time."""

    def __init__(
        self,
        paciente: dict,
        clinica_id: str,
        db: Client,
        pais: str = "PT",
        blocked_tools: list[str] | None = None,
        conversation_id: str = "",
    ) -> None:
        active_tools = (
            [t for t in _TOOLS if t["name"] not in blocked_tools]
            if blocked_tools
            else _TOOLS
        )
        super().__init__(
            system_prompt=get_whatsapp_prompt(pais),
            tools=active_tools,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=2048,
            g3_gates={"agendar_consulta": "verificar_slots"},
        )
        self._paciente = paciente
        self._clinica_id = clinica_id
        self._db = db
        self._conversation_id = conversation_id

    async def _on_g3_violation(self, attempted_tool: str, required_tool: str) -> None:
        """Log G3 gate trigger to wa_audit_log."""
        await super()._on_g3_violation(attempted_tool, required_tool)
        try:
            self._db.table("wa_audit_log").insert({
                "clinica_id": self._clinica_id,
                "conversation_id": self._conversation_id or None,
                "event_type": "g3_gate_triggered",
                "payload": {
                    "attempted_tool": attempted_tool,
                    "required_tool": required_tool,
                    "turn_number": self._turn_count,
                    "patient_id": self._paciente.get("id"),
                },
            }).execute()
        except Exception:
            logger.exception("G3 audit log insert failed | clinica=%s", self._clinica_id)

    async def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        # search_kb is async (OpenAI API call) — handled separately
        if tool_name == "search_kb":
            return await self._buscar_kb(tool_input)

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

    async def _buscar_kb(self, args: dict) -> str:
        from app.services.kb_service import search_kb
        query = args.get("query", "")
        if not query:
            return "Por favor especifica o que queres pesquisar."
        return await search_kb(self._db, query, self._clinica_id)


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


# ─── Snapshot persistence ─────────────────────────────────────────────────────

def _load_snapshot(
    db: Client, clinica_id: str, paciente_id: str, telefone: str
) -> tuple[dict, dict]:
    """
    Loads context_snapshot from wa_conversations.
    Returns (snapshot, row) — row includes updated_at for inactivity checks.
    Creates the row with a default snapshot when it doesn't exist yet.
    """
    res = (
        db.table("wa_conversations")
        .select("id, context_snapshot, updated_at")
        .eq("clinica_id", clinica_id)
        .eq("telefone", telefone)
        .limit(1)
        .execute()
    )
    if res.data:
        row = res.data[0]
        snap = row.get("context_snapshot") or {}
        return (snap if snap else default_snapshot()), row

    snap = default_snapshot()
    db.table("wa_conversations").upsert(
        {
            "clinica_id": clinica_id,
            "paciente_id": paciente_id,
            "telefone": telefone,
            "context_snapshot": snap,
        },
        on_conflict="clinica_id,telefone",
    ).execute()
    return snap, {}


def _load_playbook(db: Client, clinica_id: str) -> dict:
    """Loads agent_playbook from wa_agents. Returns {} if not configured."""
    try:
        res = (
            db.table("wa_agents")
            .select("agent_playbook")
            .eq("clinica_id", clinica_id)
            .eq("ativo", True)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0].get("agent_playbook") or {}
    except Exception:
        logger.warning("Could not load playbook for clinica=%s", clinica_id)
    return {}


def _is_new_conversation(conv_row: dict) -> bool:
    """True if last turn was > _INACTIVITY_MINUTES ago (implicit conversation end)."""
    updated_at_str = conv_row.get("updated_at")
    if not updated_at_str:
        return False
    try:
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        elapsed_min = (datetime.now(timezone.utc) - updated_at).total_seconds() / 60
        return elapsed_min > _INACTIVITY_MINUTES
    except (ValueError, TypeError):
        return False


def _save_snapshot(
    db: Client,
    clinica_id: str,
    paciente_id: str,
    telefone: str,
    snapshot: dict,
) -> None:
    """Persists the updated context_snapshot back to wa_conversations."""
    try:
        db.table("wa_conversations").upsert(
            {
                "clinica_id": clinica_id,
                "paciente_id": paciente_id,
                "telefone": telefone,
                "context_snapshot": snapshot,
            },
            on_conflict="clinica_id,telefone",
        ).execute()
    except Exception:
        logger.exception(
            "Failed to save context_snapshot | clinica=%s telefone=%s", clinica_id, telefone
        )


# ─── Entry point ──────────────────────────────────────────────────────────────

async def processar_mensagem(
    mensagem: str,
    paciente: dict,
    clinica_id: str,
    db: Client,
    pais: str = "PT",
) -> str:
    telefone: str = paciente.get("telefone", "")
    paciente_id: str = paciente["id"]
    nome: str = paciente.get("nome") or "Paciente"

    historico_res = (
        db.table("interacoes")
        .select("tipo, direcao, conteudo, created_at")
        .eq("paciente_id", paciente_id)
        .eq("clinica_id", clinica_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    consultas_res = (
        db.table("consultas")
        .select("id, data_hora, status, tipo, medicos(nome)")
        .eq("paciente_id", paciente_id)
        .gte("data_hora", datetime.now(timezone.utc).isoformat())
        .order("data_hora")
        .limit(3)
        .execute()
    )

    tem_consentimento = paciente.get("consentimento_privacidade_at") is not None

    contexto = f"""=== CONTEXTO DO PACIENTE ===
Nome: {paciente.get('nome', 'Não identificado')}
Telefone: {telefone}
Status: {paciente.get('status')}
Consentimento privacidade: {'Sim' if tem_consentimento else 'Não dado — peça antes de guardar dados de saúde'}
Tags: {', '.join(paciente.get('tags') or []) or 'Nenhuma'}

=== PRÓXIMAS CONSULTAS ===
{_formatar_consultas(consultas_res.data)}

=== HISTÓRICO RECENTE ===
{_formatar_historico(historico_res.data[::-1])}

=== MENSAGEM DO PACIENTE ===
{mensagem}"""

    # ── Load snapshot; check for inactivity gap (new conversation) ───────────
    snapshot, conv_row = _load_snapshot(db, clinica_id, paciente_id, telefone)

    if _is_new_conversation(conv_row) and snapshot.get("stage") not in ("opening", None):
        logger.info(
            "New conversation after inactivity | clinica=%s telefone=%s prev_stage=%s",
            clinica_id, telefone, snapshot.get("stage"),
        )
        # Update profile from the previous (now ended) conversation
        asyncio.create_task(
            profile_updater.update_profile(db, clinica_id, paciente_id, nome)
        )
        snapshot = default_snapshot()

    # ── Load playbook; derive blocked tools for current stage ─────────────────
    playbook = _load_playbook(db, clinica_id)
    stage_id = snapshot.get("stage", "opening")
    blocked  = get_blocked_tools(playbook, stage_id)

    # ── Build combined system prompt (profile + snapshot + playbook) ──────────
    ai_profile: dict = paciente.get("ai_profile") or {}
    profile_block  = format_profile_block(nome, ai_profile)
    snapshot_block = format_snapshot_block(snapshot)
    playbook_block = format_playbook_block(playbook, stage_id, mensagem)
    extra_system   = "\n\n".join(b for b in [profile_block, snapshot_block, playbook_block] if b)

    logger.debug(
        "Turn context | clinica=%s stage=%s blocked=%s has_profile=%s has_playbook=%s",
        clinica_id, stage_id, blocked, bool(ai_profile), bool(playbook),
    )

    agent = WhatsAppAgent(
        paciente=paciente,
        clinica_id=clinica_id,
        db=db,
        pais=pais,
        blocked_tools=blocked or None,
        conversation_id=conv_row.get("id", ""),
    )
    resposta = await agent.run(contexto, extra_system=extra_system)

    # ── Detect stage transitions; persist snapshot ────────────────────────────
    updated_snapshot = detect_stage_from_response(resposta, mensagem, snapshot)
    _save_snapshot(db, clinica_id, paciente_id, telefone, updated_snapshot)

    logger.debug(
        "Snapshot saved | stage=%s→%s turns=%s",
        snapshot.get("stage"), updated_snapshot.get("stage"),
        updated_snapshot.get("turns_in_stage"),
    )

    # ── Trigger ai_profile update when conversation ends ──────────────────────
    if updated_snapshot.get("stage") == "closing":
        logger.info(
            "Profile update triggered (closing) | clinica=%s paciente=%s",
            clinica_id, paciente_id,
        )
        asyncio.create_task(
            profile_updater.update_profile(db, clinica_id, paciente_id, nome)
        )

    return resposta
