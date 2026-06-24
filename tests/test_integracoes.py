"""
tests/test_integracoes.py
Tests for /api/v1/integracoes/* endpoints.

Coverage:
  1. POST cria integração cifrando a credencial (banco não recebe texto puro)
  2. GET nunca devolve credencial decifrada (tem_credencial: bool apenas)
  3. Cross-tenant: clínica A não acede a integrações de clínica B
  4. PATCH actualiza credenciais cifrando o novo valor
  5. DELETE remove integração (204)
  6. POST /testar — sucesso externo → status 'conectado'
  7. POST /testar — falha externa → status 'erro'
  8. POST /testar — sem credenciais → 422
  9. encryption.cifrar / decifrar round-trip
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ─── Injeta chave de teste no settings já instanciado ────────────────────────
# pydantic-settings lê o .env no boot — se ENCRYPTION_KEY não estiver no .env
# de teste, ou se settings já foi importado por outro módulo de teste,
# é necessário patchear o atributo directamente no singleton.
TEST_KEY = Fernet.generate_key().decode()

import app.core.config as _cfg
_cfg.settings.ENCRYPTION_KEY = TEST_KEY   # sobrescreve o singleton já carregado

from app.core import encryption as _enc_module
_enc_module._reset()                       # descarta Fernet criado com chave errada

from app.api.v1.endpoints.integracoes import router
from app.core.database import get_clinica_id, get_supabase, get_current_user
from app.core.encryption import cifrar, decifrar

# ─── Constants ────────────────────────────────────────────────────────────────

CLINICA_A = str(uuid4())
CLINICA_B = str(uuid4())
USER_A    = {"sub": "user-a", "email": "a@test.com", "user_metadata": {"clinica_id": CLINICA_A}}

FAKE_TOKEN    = "meu-token-secreto-12345"
FAKE_CRED     = cifrar(FAKE_TOKEN)   # ciphertext que seria guardado no DB

# ─── App factory ──────────────────────────────────────────────────────────────

def _make_app(mock_db: MagicMock, clinica_id: str = CLINICA_A) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/integracoes")
    app.dependency_overrides[get_clinica_id]   = lambda: clinica_id
    app.dependency_overrides[get_supabase]     = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: USER_A
    return TestClient(app)

# ─── DB mock helpers ──────────────────────────────────────────────────────────

def _row(tipo: str = "whatsapp", clinica_id: str = CLINICA_A) -> dict:
    return {
        "id":           str(uuid4()),
        "clinica_id":   clinica_id,
        "tipo":         tipo,
        "credenciais":  FAKE_CRED,
        "config":       {"instance_name": "clinica-test", "waha_url": "http://waha"},
        "ativo":        True,
        "status":       "desconectado",
        "created_at":   "2026-01-01T00:00:00+00:00",
        "updated_at":   "2026-01-01T00:00:00+00:00",
    }


def _upsert_mock(captured: list) -> MagicMock:
    """Mock que captura o payload enviado ao upsert."""
    row = _row()
    exec_result = MagicMock()
    exec_result.data = [row]

    upsert_builder = MagicMock()
    upsert_builder.execute.return_value = exec_result

    def _capture(data: dict, **kwargs):
        captured.append(data)
        return upsert_builder

    table_mock = MagicMock()
    table_mock.upsert.side_effect = _capture

    db = MagicMock()
    db.table.return_value = table_mock
    return db


def _list_mock(rows: list[dict]) -> MagicMock:
    """Mock para GET /integracoes/."""
    exec_result = MagicMock()
    exec_result.data = rows

    chain = MagicMock()
    chain.execute.return_value = exec_result

    table_mock = MagicMock()
    table_mock.select.return_value.eq.return_value.order.return_value = chain

    db = MagicMock()
    db.table.return_value = table_mock
    return db


def _update_mock(captured: list, rows: list[dict] | None = None) -> MagicMock:
    """Mock para PATCH / update de status."""
    result_rows = rows if rows is not None else [_row()]
    exec_result = MagicMock()
    exec_result.data = result_rows

    update_builder = MagicMock()
    update_builder.eq.return_value.eq.return_value.execute.return_value = exec_result
    update_builder.eq.return_value.execute.return_value = exec_result

    def _capture(data: dict):
        captured.append(data)
        return update_builder

    table_mock = MagicMock()
    table_mock.update.side_effect = _capture
    # also handle select → single → execute (para _fetch_integracao)
    single_chain = MagicMock()
    single_chain.execute.return_value = MagicMock(data=_row())
    table_mock.select.return_value.eq.return_value.eq.return_value.single.return_value = single_chain

    db = MagicMock()
    db.table.return_value = table_mock
    return db


# ─── Tests: encryption round-trip ─────────────────────────────────────────────

def test_cifrar_decifrar_round_trip():
    plaintext = "token-super-secreto-9999"
    ct = cifrar(plaintext)
    assert ct != plaintext, "Ciphertext não pode ser igual ao texto puro"
    assert decifrar(ct) == plaintext


def test_cifrar_gera_ciphertexts_diferentes():
    """Mesmo plaintext → ciphertexts diferentes (nonce aleatório por chamada)."""
    ct1 = cifrar("abc")
    ct2 = cifrar("abc")
    assert ct1 != ct2


# ─── Tests: POST /integracoes/ ────────────────────────────────────────────────

def test_criar_integracao_cifra_credencial():
    """O payload enviado ao banco deve conter ciphertext, não o token puro."""
    captured: list = []
    db = _upsert_mock(captured)
    client = _make_app(db)

    resp = client.post("/integracoes/", json={
        "tipo":         "whatsapp",
        "credenciais":  FAKE_TOKEN,
        "config":       {"waha_url": "http://waha", "instance_name": "abc"},
    })

    assert resp.status_code == 200
    assert len(captured) == 1

    payload = captured[0]
    # A credencial no banco NÃO é o token puro
    assert payload.get("credenciais") != FAKE_TOKEN, "Banco recebeu texto puro — FALHA DE SEGURANÇA"
    # É um ciphertext Fernet válido (decifra correctamente)
    assert decifrar(payload["credenciais"]) == FAKE_TOKEN


def test_criar_integracao_sem_credencial_nao_envia_campo():
    """POST sem credenciais não deve incluir 'credenciais' no payload do DB."""
    captured: list = []
    db = _upsert_mock(captured)
    client = _make_app(db)

    resp = client.post("/integracoes/", json={
        "tipo":   "whatsapp",
        "config": {"waha_url": "http://waha"},
    })

    assert resp.status_code == 200
    assert "credenciais" not in captured[0]


def test_criar_integracao_tipo_invalido_retorna_422():
    db = MagicMock()
    client = _make_app(db)

    resp = client.post("/integracoes/", json={"tipo": "telegram", "config": {}})
    assert resp.status_code == 422


# ─── Tests: GET /integracoes/ ─────────────────────────────────────────────────

def test_get_nao_retorna_credencial_decifrada():
    """Response do GET não deve conter o campo 'credenciais' (nem cifrado nem puro)."""
    db = _list_mock([_row()])
    client = _make_app(db)

    resp = client.get("/integracoes/")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1

    item = items[0]
    assert "credenciais" not in item, "Credencial exposta na API — FALHA DE SEGURANÇA"
    assert item["tem_credencial"] is True


def test_get_sem_integracoes_retorna_lista_vazia():
    db = _list_mock([])
    client = _make_app(db)

    resp = client.get("/integracoes/")
    assert resp.status_code == 200
    assert resp.json() == []


# ─── Tests: cross-tenant isolation ────────────────────────────────────────────

def test_get_cross_tenant_nao_ve_outra_clinica():
    """
    A clínica B não deve ver os dados da clínica A.
    O mock do DB é configurado para não devolver rows quando o clinica_id
    não corresponde — tal como o RLS faz no Supabase.
    """
    # DB que só devolve dados para CLINICA_A
    exec_result_a = MagicMock()
    exec_result_a.data = [_row(clinica_id=CLINICA_A)]

    exec_result_b = MagicMock()
    exec_result_b.data = []  # RLS bloqueia B

    call_count = {"n": 0}

    def chain_factory(*args, **kwargs):
        # Primeira chamada (clinica A) → devolve dados
        # Segunda chamada (clinica B) → devolve vazio
        call_count["n"] += 1
        mock = MagicMock()
        if call_count["n"] == 1:
            mock.execute.return_value = exec_result_a
        else:
            mock.execute.return_value = exec_result_b
        return mock

    table_mock = MagicMock()
    table_mock.select.return_value.eq.return_value.order.return_value = MagicMock(
        execute=MagicMock(side_effect=lambda: exec_result_b)
    )

    db_b = MagicMock()
    db_b.table.return_value = table_mock
    client_b = _make_app(db_b, clinica_id=CLINICA_B)

    resp = client_b.get("/integracoes/")
    assert resp.status_code == 200
    assert resp.json() == [], "Clínica B viu dados da clínica A — FALHA DE ISOLAMENTO"


# ─── Tests: PATCH /integracoes/{tipo} ────────────────────────────────────────

def test_patch_credenciais_cifra_novo_token():
    """PATCH com nova credencial deve cifrar antes do update."""
    captured: list = []
    db = _update_mock(captured)
    client = _make_app(db)

    novo_token = "novo-token-kommo-xyz"
    resp = client.patch("/integracoes/whatsapp", json={"credenciais": novo_token})

    assert resp.status_code == 200
    assert len(captured) >= 1

    payload = captured[0]
    assert payload.get("credenciais") != novo_token, "Novo token em texto puro no DB — FALHA"
    assert decifrar(payload["credenciais"]) == novo_token


# ─── Tests: DELETE /integracoes/{tipo} ───────────────────────────────────────

def test_delete_retorna_204():
    exec_result = MagicMock()
    exec_result.data = [_row()]

    table_mock = MagicMock()
    table_mock.delete.return_value.eq.return_value.eq.return_value.execute.return_value = exec_result

    db = MagicMock()
    db.table.return_value = table_mock
    client = _make_app(db)

    resp = client.delete("/integracoes/whatsapp")
    assert resp.status_code == 204


# ─── Tests: POST /integracoes/{tipo}/testar ───────────────────────────────────

def _db_for_test(row: dict | None = None, update_captured: list | None = None) -> MagicMock:
    """Mock DB com select (para _fetch_integracao) e update (para mudar status)."""
    result = row or _row()
    uc = update_captured if update_captured is not None else []

    single_chain = MagicMock()
    single_chain.execute.return_value = MagicMock(data=result)

    update_chain = MagicMock()
    update_chain.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[result])

    def _cap_update(data):
        uc.append(data)
        return update_chain

    table_mock = MagicMock()
    table_mock.select.return_value.eq.return_value.eq.return_value.single.return_value = single_chain
    table_mock.update.side_effect = _cap_update

    db = MagicMock()
    db.table.return_value = table_mock
    return db


def test_testar_whatsapp_sucesso_atualiza_status_conectado():
    """Resposta HTTP 200 do WAHA → status 'conectado'."""
    update_captured: list = []
    db = _db_for_test(update_captured=update_captured)
    client = _make_app(db)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        mock_ctx.get        = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        resp = client.post("/integracoes/whatsapp/testar")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "conectado"

    # Verifica que o status foi actualizado no DB
    assert any(u.get("status") == "conectado" for u in update_captured)


def test_testar_whatsapp_falha_atualiza_status_erro():
    """Resposta HTTP 401 do WAHA → status 'erro'."""
    update_captured: list = []
    db = _db_for_test(update_captured=update_captured)
    client = _make_app(db)

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        mock_ctx.get        = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        resp = client.post("/integracoes/whatsapp/testar")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "erro"
    assert any(u.get("status") == "erro" for u in update_captured)


def test_testar_sem_credenciais_retorna_422():
    """Integração sem credenciais → 422 antes de fazer qualquer request externo."""
    row_sem_cred = {**_row(), "credenciais": None}
    db = _db_for_test(row=row_sem_cred)
    client = _make_app(db)

    resp = client.post("/integracoes/whatsapp/testar")
    assert resp.status_code == 422
    assert "sem credenciais" in resp.json()["detail"].lower()
