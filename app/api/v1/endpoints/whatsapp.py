"""
whatsapp.py — WhatsApp webhook + connection management (Waha).

Multi-tenancy
-------------
  Each clinic registers one (or more) Waha sessions in
  whatsapp_connections(instance_name, clinica_id, phone_number).
  instance_name == Waha session name.

  When an inbound webhook arrives, the `session` field in the payload is
  used to look up the clinica_id — no hardcoded tenant anywhere.

  The lookup uses the Supabase *service key* (bypasses RLS), which is correct
  because the webhook has no user JWT. All subsequent data operations are
  scoped to the resolved clinica_id to maintain full tenant isolation.

Waha webhook payload (event = "message"):
  {
    "event": "message",
    "session": "<session_name>",
    "payload": {
      "from": "<phone>@c.us",
      "fromMe": false,
      "body": "<text>",
      "hasMedia": false,
      ...
    }
  }

Endpoints
---------
  POST /webhook            — receives Waha events (no auth)
  POST /connections        — register a new Waha session   (JWT required)
  GET  /connections        — list connections for this clinic (JWT required)
  DELETE /connections/{id} — deactivate a connection          (JWT required)
"""

import asyncio
import logging
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from supabase import Client

from app.agents.router import Router
from app.core.config import settings
from app.core.database import get_clinica_id, get_supabase
from app.schemas.schemas import (
    WhatsAppConnectionCreate,
    WhatsAppConnectionOut,
)
from app.services import message_buffer
from app.services.agent_dispatcher import dispatch_agent
from app.services.timeline_service import registrar_interacao
from app.services.wa_chunker import calculate_delay_ms, split_into_chunks

logger = logging.getLogger(__name__)
router = APIRouter()

_BUFFER_TTL_SECONDS = 12

# Stateless Router instance — None when ANTHROPIC_API_KEY not configured
_router: Router | None = Router(api_key=settings.ANTHROPIC_API_KEY) if settings.ANTHROPIC_API_KEY else None


# ─── Connection management ────────────────────────────────────────────────────

@router.post("/connections", response_model=WhatsAppConnectionOut, status_code=201)
def registar_conexao(
    body: WhatsAppConnectionCreate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    """
    Regista uma nova sessão Waha para esta clínica.
    instance_name deve ser único em todo o sistema.
    """
    # Rejeita duplicados — instance_name é unique na tabela
    existente = (
        db.table("whatsapp_connections")
        .select("id")
        .eq("instance_name", body.instance_name)
        .execute()
    )
    if existente.data:
        raise HTTPException(
            status_code=409,
            detail=f"Instância '{body.instance_name}' já está registada.",
        )

    res = db.table("whatsapp_connections").insert({
        "clinica_id": clinica_id,
        "instance_name": body.instance_name,
        "phone_number": body.phone_number,
        "ativo": True,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar conexão.")

    logger.info(
        "WhatsApp connection registered | instance=%s clinica=%s",
        body.instance_name,
        clinica_id,
    )
    return res.data[0]


@router.get("/connections", response_model=list[WhatsAppConnectionOut])
def listar_conexoes(
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    """Lista todas as conexões WhatsApp desta clínica."""
    return (
        db.table("whatsapp_connections")
        .select("*")
        .eq("clinica_id", clinica_id)
        .order("created_at")
        .execute()
        .data
    )


@router.delete("/connections/{connection_id}", status_code=204)
def desativar_conexao(
    connection_id: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client = Depends(get_supabase),
):
    """
    Desactiva uma conexão (soft delete).
    Mensagens desta instância serão ignoradas pelo webhook.
    """
    res = (
        db.table("whatsapp_connections")
        .update({"ativo": False})
        .eq("id", connection_id)
        .eq("clinica_id", clinica_id)   # garante que só desactiva o seu próprio
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")


# ─── Tenant resolver ──────────────────────────────────────────────────────────

def _resolver_clinica(db: Client, instance_name: str) -> str | None:
    """
    Resolve clinica_id a partir do session name do Waha.

    Uses the service-key client (bypasses RLS) — correct for this path
    because inbound webhooks carry no user JWT.

    Returns None when the instance is unknown or inactive.
    """
    res = (
        db.table("whatsapp_connections")
        .select("clinica_id")
        .eq("instance_name", instance_name)
        .eq("ativo", True)
        .single()
        .execute()
    )
    return res.data["clinica_id"] if res.data else None


# ─── Webhook ──────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Client = Depends(get_supabase),
):
    """
    Receives all events from Waha.
    Returns 200 immediately; processing runs in the background.

    No authentication — Waha does not send a Bearer token no webhook.
    Tenant isolation is enforced by resolving clinica_id from session name.
    """
    payload = await request.json()
    background_tasks.add_task(_handle_message, payload, db)
    return {"status": "received"}


async def _handle_message(payload: dict, db: Client) -> None:
    """
    Inbound message pipeline — steps 1-2 run immediately per webhook call.
    Steps 3-8 are deferred via message_buffer and run once per debounced turn.

    1.  Validate event type and extract fields
    2.  Resolve clinica_id from instance_name  ← multi-tenant pivot
    3.  Buffer text; schedule _process_turn after BUFFER_TTL seconds of silence
        (steps 3–8 run inside _process_turn when the buffer flushes)
    """
    try:
        # ── 1. Validate ────────────────────────────────────────────────────
        if payload.get("event") != "message":
            return

        msg_data = payload.get("payload", {})
        if msg_data.get("fromMe", False):
            return  # ignore self-sent messages

        instance_name: str = payload.get("session", "")
        # Waha envia "351912345678@c.us" — normaliza para só dígitos
        telefone: str = (
            msg_data.get("from", "")
            .replace("@c.us", "")
            .replace("@s.whatsapp.net", "")
        )
        texto: str = msg_data.get("body", "")

        if not instance_name or not telefone or not texto:
            logger.debug(
                "Ignoring incomplete payload | instance=%s telefone=%s",
                instance_name,
                telefone,
            )
            return

        # ── 2. Resolve tenant ───────────────────────────────────────────────
        clinica_id = _resolver_clinica(db, instance_name)
        if not clinica_id:
            logger.warning(
                "Unknown or inactive instance '%s' — message dropped.", instance_name
            )
            return

        logger.info(
            "Inbound message | instance=%s clinica=%s telefone=%s",
            instance_name,
            clinica_id,
            telefone,
        )

        # ── 3. Buffer + debounce ────────────────────────────────────────────
        async def on_flush(full_text: str) -> None:
            await _process_turn(
                clinica_id=clinica_id,
                instance_name=instance_name,
                telefone=telefone,
                texto=full_text,
                db=db,
            )

        await message_buffer.push(
            tenant_id=clinica_id,
            phone=telefone,
            text=texto,
            ttl=_BUFFER_TTL_SECONDS,
            on_flush=on_flush,
        )

    except Exception:
        logger.exception("WhatsApp handler error")


async def _process_turn(
    *,
    clinica_id: str,
    instance_name: str,
    telefone: str,
    texto: str,
    db: Client,
) -> None:
    """
    Full agent pipeline for one debounced turn (steps 3–8).
    Called by message_buffer once the patient has stopped typing.

    3.  Find or create the patient record
    4.  Classify intent via two-tier Router
    5.  Record inbound interaction in the timeline
    6.  Dispatch to the correct agent
    7.  Send reply via Waha (scoped session)
    8.  Record outbound interaction in the timeline
    """
    try:
        # ── 3. Find or create patient ───────────────────────────────────────
        res = (
            db.table("pacientes")
            .select("*")
            .eq("telefone", telefone)
            .eq("clinica_id", clinica_id)
            .execute()
        )
        if res.data:
            paciente = res.data[0]
        else:
            paciente = (
                db.table("pacientes")
                .insert({
                    "clinica_id": clinica_id,
                    "nome": f"WhatsApp {telefone}",
                    "telefone": telefone,
                    "origem": "whatsapp",
                    "status": "lead",
                    "consentimento_rgpd_at": None,
                    "tags": [],
                })
                .execute()
                .data[0]
            )

        # ── 4. Classify intent ──────────────────────────────────────────────
        if _router is None:
            logger.warning("WhatsApp agent inactivo: ANTHROPIC_API_KEY não configurada")
            return
        route = await _router.classify(texto)
        logger.info(
            "Router → %s (confidence=%.0f%%, tier=%s) | patient=%s",
            route.agent_name,
            route.confidence * 100,
            route.tier.value,
            paciente["id"],
        )

        # ── 5. Record inbound ───────────────────────────────────────────────
        registrar_interacao(db, {
            "clinica_id": clinica_id,
            "paciente_id": paciente["id"],
            "tipo": "whatsapp",
            "direcao": "entrada",
            "conteudo": texto,
            "criado_por": "sistema",
        })

        # ── 6. Dispatch to agent ────────────────────────────────────────────
        resposta = await dispatch_agent(
            route=route,
            texto=texto,
            paciente=paciente,
            clinica_id=clinica_id,
            db=db,
        )

        # ── 7. Send reply ───────────────────────────────────────────────────
        await _enviar_whatsapp(
            telefone=telefone,
            mensagem=resposta,
            instance_name=instance_name,
        )

        # ── 8. Record outbound ──────────────────────────────────────────────
        registrar_interacao(db, {
            "clinica_id": clinica_id,
            "paciente_id": paciente["id"],
            "tipo": "whatsapp",
            "direcao": "saida",
            "conteudo": resposta,
            "criado_por": route.agent_name,
        })

    except Exception:
        logger.exception(
            "WhatsApp process_turn error | clinica=%s telefone=%s", clinica_id, telefone
        )


# ─── Startup recovery factory ────────────────────────────────────────────────

def make_flush_callback(tenant_id: str, phone: str):
    """
    Returns an on_flush coroutine for message_buffer.recover().
    Resolves instance_name from the DB at flush time so that the factory
    can be constructed before any DB call is needed.
    """
    async def on_flush(text: str) -> None:
        db = get_supabase()
        res = (
            db.table("whatsapp_connections")
            .select("instance_name")
            .eq("clinica_id", tenant_id)
            .eq("ativo", True)
            .limit(1)
            .execute()
        )
        if not res.data:
            logger.warning(
                "Recovery: no active WhatsApp connection for clinica=%s — dropping buffer",
                tenant_id,
            )
            return
        await _process_turn(
            clinica_id=tenant_id,
            instance_name=res.data[0]["instance_name"],
            telefone=phone,
            texto=text,
            db=db,
        )

    return on_flush


# ─── Waha send helper ─────────────────────────────────────────────────────────

def _normalize_chat_id(telefone: str) -> str:
    """Normaliza para '<digits>@c.us' independente do formato de entrada."""
    return (
        telefone.lstrip("+")
        .replace("@c.us", "")
        .replace("@s.whatsapp.net", "")
        + "@c.us"
    )


async def _waha_post(client: httpx.AsyncClient, url: str, headers: dict, body: dict) -> int:
    """POST helper; retorna o status code."""
    res = await client.post(url, json=body, headers=headers)
    return res.status_code


async def _enviar_whatsapp(
    telefone: str,
    mensagem: str,
    instance_name: str,
) -> None:
    """
    Envia a resposta do agente em chunks humanizados via WAHA Plus.

    Para cada chunk:
      1. Dispara startTyping (typing indicator) — ignorado com fallback se WAHA
         não suportar o endpoint.
      2. Aguarda o delay calculado pela velocidade de digitação simulada.
      3. Envia o chunk via sendText.
      4. Aguarda 400 ms antes do próximo chunk.

    Phone format: WAHA espera "<digits>@c.us".
    """
    chat_id = _normalize_chat_id(telefone)
    headers = {
        "X-Api-Key": settings.WAHA_API_KEY,
        "Content-Type": "application/json",
    }
    url_send   = f"{settings.WAHA_URL}/api/sendText"
    url_typing = f"{settings.WAHA_URL}/api/startTyping"

    chunks = split_into_chunks(mensagem)
    if not chunks:
        return

    total = len(chunks)
    logger.debug("Sending %d chunk(s) to %s | session=%s", total, telefone, instance_name)

    if os.environ.get("WAHA_DEV_MODE", "").lower() == "true":
        for i, chunk in enumerate(chunks, 1):
            logger.info("[DEV MODE] Would send chunk %d/%d: %s", i, total, chunk)
        return

    async with httpx.AsyncClient(timeout=10) as client:
        for i, chunk in enumerate(chunks):
            delay_ms = calculate_delay_ms(chunk)

            # ── Typing indicator ──────────────────────────────────────────────
            try:
                status = await _waha_post(
                    client,
                    url_typing,
                    headers,
                    {"chatId": chat_id, "session": instance_name},
                )
                if status not in (200, 201, 204):
                    logger.debug("startTyping not supported (status=%d) — skipping", status)
            except Exception:
                logger.debug("startTyping unavailable — continuing without typing indicator")

            # ── Simulated typing delay ────────────────────────────────────────
            await asyncio.sleep(delay_ms / 1000)

            # ── Send chunk ───────────────────────────────────────────────────
            status = await _waha_post(
                client,
                url_send,
                headers,
                {"chatId": chat_id, "text": chunk, "session": instance_name},
            )
            if status not in (200, 201):
                logger.error(
                    "Waha sendText error | session=%s chunk=%d/%d status=%d",
                    instance_name, i + 1, len(chunks), status,
                )

            # ── Inter-chunk pause ─────────────────────────────────────────────
            if i < len(chunks) - 1:
                await asyncio.sleep(0.4)
