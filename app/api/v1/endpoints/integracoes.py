"""
integracoes.py — CRUD de integrações de terceiros por clínica.

Conectores suportados: 'whatsapp' (WAHA), 'kommo'.

Segurança:
  • clinica_id SEMPRE extraído do JWT — nunca do body.
  • Credenciais NUNCA devolvidas decifradas na API pública.
  • Cifragem com Fernet (app.core.encryption) antes de qualquer INSERT/UPDATE.

Endpoints CRUD:
  POST   /integracoes/                      — upsert por tipo
  GET    /integracoes/                      — lista (sem credenciais)
  PATCH  /integracoes/{tipo}               — actualiza campos
  DELETE /integracoes/{tipo}               — remove

Endpoints WhatsApp/QR:
  POST   /integracoes/whatsapp/conectar    — inicia sessão WAHA e devolve QR base64
  GET    /integracoes/whatsapp/status-sessao — polling do estado da sessão

Endpoints de teste:
  POST   /integracoes/{tipo}/testar        — testa conexão real

WAHA API utilizada (v2024+):
  POST   {waha_url}/api/sessions            — cria/inicia sessão
  POST   {waha_url}/api/sessions/{name}/start — reinicia sessão existente
  GET    {waha_url}/api/sessions/{name}     — status da sessão
  GET    {waha_url}/api/{name}/auth/qr      — QR code como PNG (para scan)
  Statuses WAHA: STOPPED | STARTING | SCAN_QR_CODE | WORKING | FAILED
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.database import get_supabase, get_clinica_id
from app.core.config import settings
from app.core.encryption import cifrar, decifrar

logger = logging.getLogger(__name__)
router = APIRouter()

TIPOS_VALIDOS = {"whatsapp", "kommo"}


# ─── Schemas ──────────────────────────────────────────────────────────────────

class IntegracaoUpsert(BaseModel):
    tipo: str
    credenciais: str | None = None   # plaintext; cifrado antes de gravar
    config: dict = {}
    ativo: bool = True


class IntegracaoUpdate(BaseModel):
    credenciais: str | None = None   # None = não altera
    config: dict | None = None
    ativo: bool | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sanitize_output(row: dict) -> dict:
    """
    Remove a coluna 'credenciais' cifrada e substitui por `tem_credencial: bool`.
    O ciphertext jamais sai pela API — nem cifrado, nem decifrado.
    """
    cred = row.pop("credenciais", None)
    row["tem_credencial"] = bool(cred)
    return row


def _fetch_integracao(db: Client, clinica_id: str, tipo: str) -> dict:
    """Obtém integração ou lança 404."""
    res = (
        db.table("integracoes")
        .select("*")
        .eq("clinica_id", clinica_id)
        .eq("tipo", tipo)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Integração '{tipo}' não encontrada.")
    return res.data


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("/", status_code=200)
def upsert_integracao(
    body: IntegracaoUpsert,
    clinica_id: str = Depends(get_clinica_id),
    db: Client      = Depends(get_supabase),
) -> dict:
    """
    Cria ou substitui a integração do tipo especificado.
    Se já existir um registo para (clinica_id, tipo), actualiza.
    """
    if body.tipo not in TIPOS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo inválido: '{body.tipo}'. Use: {sorted(TIPOS_VALIDOS)}"
        )

    payload: dict[str, Any] = {
        "clinica_id": clinica_id,
        "tipo":       body.tipo,
        "config":     body.config,
        "ativo":      body.ativo,
        "status":     "desconectado",
    }

    if body.credenciais:
        payload["credenciais"] = cifrar(body.credenciais)

    res = (
        db.table("integracoes")
        .upsert(payload, on_conflict="clinica_id,tipo")
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao guardar integração.")

    return _sanitize_output(dict(res.data[0]))


@router.get("/")
def listar_integracoes(
    clinica_id: str = Depends(get_clinica_id),
    db: Client      = Depends(get_supabase),
) -> list[dict]:
    """Lista todas as integrações da clínica. Credenciais NUNCA expostas."""
    res = (
        db.table("integracoes")
        .select("*")
        .eq("clinica_id", clinica_id)
        .order("tipo")
        .execute()
    )
    return [_sanitize_output(dict(r)) for r in (res.data or [])]


@router.patch("/{tipo}")
def atualizar_integracao(
    tipo: str,
    body: IntegracaoUpdate,
    clinica_id: str = Depends(get_clinica_id),
    db: Client      = Depends(get_supabase),
) -> dict:
    """
    Actualiza campos da integração. Credenciais: só actualiza se `credenciais`
    vier preenchido no body — None mantém o valor existente.
    """
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Tipo inválido: '{tipo}'.")

    updates: dict[str, Any] = {}
    if body.config is not None:
        updates["config"] = body.config
    if body.ativo is not None:
        updates["ativo"] = body.ativo
    if body.credenciais:
        updates["credenciais"] = cifrar(body.credenciais)

    if not updates:
        raise HTTPException(status_code=422, detail="Nenhum campo para actualizar.")

    res = (
        db.table("integracoes")
        .update(updates)
        .eq("clinica_id", clinica_id)
        .eq("tipo", tipo)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Integração '{tipo}' não encontrada.")

    return _sanitize_output(dict(res.data[0]))


@router.delete("/{tipo}", status_code=204)
def remover_integracao(
    tipo: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client      = Depends(get_supabase),
):
    """Remove a integração do tipo indicado."""
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Tipo inválido: '{tipo}'.")

    db.table("integracoes").delete().eq("clinica_id", clinica_id).eq("tipo", tipo).execute()


# ─── WhatsApp / QR Code ───────────────────────────────────────────────────────

def _waha_headers(api_key: str) -> dict:
    return {"X-Api-Key": api_key, "Content-Type": "application/json"}


def _resolve_waha_creds(integracao: dict) -> tuple[str, str, str]:
    """Devolve (waha_url, instance_name, api_key) ou lança 422."""
    config = integracao.get("config") or {}
    waha_url      = (config.get("waha_url") or settings.WAHA_URL).rstrip("/")
    instance_name = config.get("instance_name", "")
    raw_cred = integracao.get("credenciais")
    api_key  = decifrar(raw_cred) if raw_cred else settings.WAHA_API_KEY

    if not waha_url:
        raise HTTPException(422, "waha_url não configurado. Guarde a configuração primeiro.")
    if not instance_name:
        raise HTTPException(422, "Nome da sessão não configurado. Guarde a configuração primeiro.")
    return waha_url, instance_name, api_key


@router.post("/whatsapp/conectar")
async def iniciar_sessao_qr(
    clinica_id: str = Depends(get_clinica_id),
    db: Client      = Depends(get_supabase),
) -> dict:
    """
    Inicia (ou reinicia) a sessão WAHA e devolve o QR Code como data URL base64.

    Fluxo:
      1. Tenta criar sessão via POST /api/sessions.
         Se já existe (409) faz POST /api/sessions/{name}/start para reiniciar.
      2. Aguarda 1.5s para WAHA gerar o QR.
      3. Busca QR como imagem PNG e converte para data URL.
      4. O cliente faz polling em /whatsapp/status-sessao até WORKING.

    Pré-requisito: integração 'whatsapp' guardada com waha_url + instance_name.
    A credencial (api_key) é decifrada internamente — nunca exposta na response.
    """
    integracao = _fetch_integracao(db, clinica_id, "whatsapp")
    waha_url, instance_name, api_key = _resolve_waha_creds(integracao)
    hdrs = _waha_headers(api_key)

    # URL que o WAHA usará para enviar eventos ao backend.
    # Configurada explicitamente na sessão (mecanismo fiável, funciona em todas
    # as versões do WAHA) — não depende apenas de variáveis de ambiente globais.
    webhook_url = (
        f"{settings.BACKEND_WEBHOOK_URL.rstrip('/')}"
        f"/api/v1/whatsapp/webhook"
    )
    session_config = {
        "name": instance_name,
        "config": {
            "webhooks": [
                {
                    "url":    webhook_url,
                    "events": ["message", "session.status"],
                }
            ]
        },
    }

    logger.info(
        "Iniciando sessão WAHA | session=%s webhook=%s",
        instance_name, webhook_url,
    )

    async with httpx.AsyncClient(timeout=15) as client:
        # Tenta criar a sessão (com webhook configurado no body)
        create_res = await client.post(
            f"{waha_url}/api/sessions",
            json=session_config,
            headers=hdrs,
        )

        if create_res.status_code == 409:
            # Sessão já existe — para, recria com a config de webhook actualizada
            await client.post(
                f"{waha_url}/api/sessions/{instance_name}/stop",
                headers=hdrs,
            )
            await asyncio.sleep(0.5)
            # Recria com webhook configurado
            create_res = await client.post(
                f"{waha_url}/api/sessions",
                json=session_config,
                headers=hdrs,
            )
            # Se ainda der 409, inicia directamente
            if create_res.status_code == 409:
                await client.post(
                    f"{waha_url}/api/sessions/{instance_name}/start",
                    headers=hdrs,
                )
        elif create_res.status_code not in (200, 201):
            raise HTTPException(
                502,
                f"WAHA não aceitou criar a sessão (HTTP {create_res.status_code}): "
                f"{create_res.text[:120]}"
            )

        # Aguarda WAHA gerar o QR
        await asyncio.sleep(1.5)

        # Obtém QR como imagem PNG
        qr_res = await client.get(
            f"{waha_url}/api/{instance_name}/auth/qr",
            headers=hdrs,
        )

    if qr_res.status_code != 200:
        raise HTTPException(
            502,
            f"WAHA não devolveu QR Code (HTTP {qr_res.status_code}). "
            "A sessão pode estar ainda a iniciar — tente novamente em alguns segundos."
        )

    # Converte PNG → data URL base64
    content_type = qr_res.headers.get("content-type", "image/png").split(";")[0]
    qr_b64 = base64.b64encode(qr_res.content).decode()

    # Actualiza status para 'desconectado' (aguardando scan)
    db.table("integracoes").update({"status": "desconectado"}).eq(
        "clinica_id", clinica_id
    ).eq("tipo", "whatsapp").execute()

    logger.info(
        "QR Code gerado | clinica=%s session=%s", clinica_id, instance_name
    )

    return {
        "qr_code":   f"data:{content_type};base64,{qr_b64}",
        "session":   instance_name,
        "instrucao": (
            "Abra o WhatsApp → Aparelhos Ligados → Ligar um aparelho "
            "→ aponte a câmara para este QR Code."
        ),
    }


@router.get("/whatsapp/status-sessao")
async def status_sessao_waha(
    clinica_id: str = Depends(get_clinica_id),
    db: Client      = Depends(get_supabase),
) -> dict:
    """
    Verifica o estado actual da sessão WAHA (chamado em polling pelo frontend).

    Devolve:
      waha_status  — STOPPED | STARTING | SCAN_QR_CODE | WORKING | FAILED
      conectado    — True quando WORKING
      telefone     — número vinculado quando conectado ("5511999@c.us")
      nome         — nome do WhatsApp quando conectado

    Quando WORKING, actualiza automaticamente integracoes.status = 'conectado'.
    """
    integracao = _fetch_integracao(db, clinica_id, "whatsapp")
    waha_url, instance_name, api_key = _resolve_waha_creds(integracao)

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(
                f"{waha_url}/api/sessions/{instance_name}",
                headers=_waha_headers(api_key),
            )
    except httpx.RequestError as exc:
        return {"waha_status": "erro", "conectado": False, "detalhe": str(exc)}

    if res.status_code != 200:
        return {
            "waha_status": "erro",
            "conectado":   False,
            "detalhe":     f"HTTP {res.status_code}: {res.text[:80]}",
        }

    data         = res.json()
    waha_status  = data.get("status", "UNKNOWN")
    me           = data.get("me") or {}
    conectado    = waha_status == "WORKING"

    if conectado:
        db.table("integracoes").update({"status": "conectado"}).eq(
            "clinica_id", clinica_id
        ).eq("tipo", "whatsapp").execute()

    logger.debug(
        "Status sessão WAHA | clinica=%s session=%s status=%s",
        clinica_id, instance_name, waha_status,
    )

    return {
        "waha_status": waha_status,
        "conectado":   conectado,
        "telefone":    me.get("id", ""),        # "5511999999999@c.us"
        "nome":        me.get("pushName", ""),
    }


# ─── Testar conexão ───────────────────────────────────────────────────────────

@router.post("/{tipo}/testar")
async def testar_integracao(
    tipo: str,
    clinica_id: str = Depends(get_clinica_id),
    db: Client      = Depends(get_supabase),
) -> dict:
    """
    Testa a conexão real com o serviço externo.
    A credencial é decifrada INTERNAMENTE — nunca sai na response.
    Actualiza o campo `status` no DB e devolve o resultado do teste.
    """
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Tipo inválido: '{tipo}'.")

    integracao = _fetch_integracao(db, clinica_id, tipo)

    raw_cred = integracao.get("credenciais")
    config   = integracao.get("config") or {}

    if not raw_cred:
        raise HTTPException(
            status_code=422,
            detail="Integração sem credenciais configuradas. Configure antes de testar."
        )

    try:
        token = decifrar(raw_cred)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    novo_status = "erro"
    detalhe: str | None = None

    try:
        if tipo == "whatsapp":
            novo_status, detalhe = await _testar_waha(config, token)
        elif tipo == "kommo":
            novo_status, detalhe = await _testar_kommo(config, token)
    except httpx.RequestError as exc:
        detalhe = f"Sem resposta do serviço: {exc}"
        novo_status = "erro"

    # Actualiza status no DB
    db.table("integracoes").update({"status": novo_status}).eq(
        "clinica_id", clinica_id
    ).eq("tipo", tipo).execute()

    logger.info(
        "Teste de integração | tipo=%s clinica=%s status=%s",
        tipo, clinica_id, novo_status,
    )

    return {
        "tipo":   tipo,
        "status": novo_status,
        "ok":     novo_status == "conectado",
        "detalhe": detalhe,
    }


async def _testar_waha(config: dict, api_key: str) -> tuple[str, str]:
    """Testa sessão WAHA. Devolve (status, detalhe)."""
    waha_url      = config.get("waha_url") or settings.WAHA_URL
    instance_name = config.get("instance_name", "")

    if not waha_url:
        return "erro", "waha_url não configurado."

    url = f"{waha_url.rstrip('/')}/api/sessions/{instance_name}" if instance_name else f"{waha_url.rstrip('/')}/api/sessions"

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(url, headers={"X-Api-Key": api_key})

    if res.status_code in (200, 201):
        return "conectado", f"Sessão activa (HTTP {res.status_code})"
    return "erro", f"HTTP {res.status_code}: {res.text[:120]}"


async def _testar_kommo(config: dict, token: str) -> tuple[str, str]:
    """Testa token Kommo via GET /api/v4/account. Devolve (status, detalhe)."""
    subdomain = config.get("subdomain", "")
    if not subdomain:
        return "erro", "Subdomínio Kommo não configurado."

    url = f"https://{subdomain}.kommo.com/api/v4/account"
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if res.status_code == 200:
        return "conectado", "Autenticação Kommo válida."
    if res.status_code == 401:
        return "erro", "Token inválido ou expirado (HTTP 401)."
    return "erro", f"HTTP {res.status_code}: {res.text[:120]}"
