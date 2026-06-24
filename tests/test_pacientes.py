"""
tests/test_pacientes.py
Unit tests for:
  - POST /pacientes/ endpoint (consentimento_privacidade field handling)
  - Fiscal document validators (NIF/CPF/CNPJ with checksum)
  - Agent locale selection (system prompt language by pais)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.pacientes import router
from app.core.database import get_clinica_id, get_supabase
from app.core.locale import validar_cpf_br, validar_cnpj_br, validar_nif_pt, validar_documento_fiscal

FAKE_CLINICA_ID = str(uuid4())

PACIENTE_BASE_PT = {
    "nome": "Ana Costa",
    "telefone": "+351912345678",
    "origem": "balcao",
    "status": "lead",
    "tags": [],
}

PACIENTE_BASE_BR = {
    "nome": "Carlos Souza",
    "telefone": "+5511999990000",
    "origem": "balcao",
    "status": "lead",
    "tags": [],
}


def _build_client(mock_db: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/pacientes")
    app.dependency_overrides[get_clinica_id] = lambda: FAKE_CLINICA_ID
    app.dependency_overrides[get_supabase] = lambda: mock_db
    return TestClient(app)


def _make_db_mock(captured: dict, pais: str = "PT") -> MagicMock:
    """Supabase mock that captures insert payload and returns a valid row."""
    fake_row = {
        "id": str(uuid4()),
        "clinica_id": FAKE_CLINICA_ID,
        "nome": "Ana Costa",
        "telefone": "+351912345678",
        "email": None,
        "documento_fiscal": None,
        "data_nascimento": None,
        "genero": None,
        "origem": "balcao",
        "status": "lead",
        "tags": [],
        "notas": None,
        "consentimento_privacidade_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    execute_result = MagicMock()
    execute_result.data = [fake_row]

    insert_builder = MagicMock()
    insert_builder.execute.return_value = execute_result

    def _capture_insert(data: dict):
        captured["payload"] = data
        return insert_builder

    # clinica lookup (for pais resolution)
    clinica_result = MagicMock()
    clinica_result.data = {"pais": pais}

    clinica_chain = MagicMock()
    clinica_chain.execute.return_value = clinica_result

    table_builder = MagicMock()
    table_builder.insert.side_effect = _capture_insert
    # Chain for clinica select: .select().eq().single().execute()
    table_builder.select.return_value.eq.return_value.single.return_value = clinica_chain

    db = MagicMock()
    db.table.return_value = table_builder
    return db


# ─── Endpoint: consentimento_privacidade ──────────────────────────────────────

def test_consentimento_true_sets_consentimento_privacidade_at():
    """When consentimento_privacidade=True, consentimento_privacidade_at must be a UTC
    timestamp and the bool field must NOT be sent to the DB."""
    captured: dict = {}
    client = _build_client(_make_db_mock(captured))

    resp = client.post("/pacientes/", json={**PACIENTE_BASE_PT, "consentimento_privacidade": True})

    assert resp.status_code == 201

    payload = captured["payload"]
    assert "consentimento_privacidade" not in payload, (
        "bool field must not reach DB — no such column"
    )
    assert payload.get("consentimento_privacidade_at") is not None, (
        "consentimento_privacidade_at must be set when consent=True"
    )
    dt = datetime.fromisoformat(payload["consentimento_privacidade_at"])
    assert dt.tzinfo is not None, "timestamp must be timezone-aware (UTC)"


def test_consentimento_false_leaves_privacidade_at_null():
    """When consentimento_privacidade=False, consentimento_privacidade_at must be absent."""
    captured: dict = {}
    client = _build_client(_make_db_mock(captured))

    resp = client.post("/pacientes/", json={**PACIENTE_BASE_PT, "consentimento_privacidade": False})

    assert resp.status_code == 201

    payload = captured["payload"]
    assert "consentimento_privacidade" not in payload
    assert payload.get("consentimento_privacidade_at") is None


# ─── Validators: NIF (Portugal) ───────────────────────────────────────────────

def test_nif_valido_pt():
    assert validar_nif_pt("500000000") is True


def test_nif_invalido_checksum():
    # All-ones: checksum wrong (expected=0, got=1)
    assert validar_nif_pt("111111111") is False


def test_nif_invalido_comprimento():
    assert validar_nif_pt("12345678") is False    # 8 digits
    assert validar_nif_pt("1234567890") is False  # 10 digits


def test_nif_aceita_formatacao():
    # Spaces stripped
    assert validar_nif_pt("500 000 000") is True


# ─── Validators: CPF (Brazil) ─────────────────────────────────────────────────

def test_cpf_valido_br():
    # Known-valid CPF: 529.982.247-25
    assert validar_cpf_br("529.982.247-25") is True
    assert validar_cpf_br("52998224725") is True


def test_cpf_invalido_digitos_iguais():
    # 111.111.111-11 — all same digits → rejected immediately
    assert validar_cpf_br("111.111.111-11") is False
    assert validar_cpf_br("00000000000") is False


def test_cpf_invalido_checksum():
    # Change last digit of valid CPF — wrong checksum
    assert validar_cpf_br("529.982.247-26") is False


def test_cpf_invalido_comprimento():
    assert validar_cpf_br("1234567890") is False    # 10 digits
    assert validar_cpf_br("123456789012") is False  # 12 digits


# ─── Validators: CNPJ (Brazil) ────────────────────────────────────────────────

def test_cnpj_valido_br():
    # 11.222.333/0001-81 (verified above in architecture session)
    assert validar_cnpj_br("11.222.333/0001-81") is True
    assert validar_cnpj_br("11222333000181") is True


def test_cnpj_invalido_digitos_iguais():
    assert validar_cnpj_br("11111111111111") is False


def test_cnpj_invalido_checksum():
    # Wrong last digit
    assert validar_cnpj_br("11.222.333/0001-82") is False


def test_cnpj_invalido_comprimento():
    assert validar_cnpj_br("1122233300018") is False   # 13 digits
    assert validar_cnpj_br("112223330001812") is False  # 15 digits


# ─── validar_documento_fiscal dispatcher ──────────────────────────────────────

def test_validar_documento_fiscal_pt_nif_valido():
    # Should not raise
    validar_documento_fiscal("500000000", "PT", "paciente")


def test_validar_documento_fiscal_pt_nif_invalido():
    with pytest.raises(ValueError, match="NIF inválido"):
        validar_documento_fiscal("111111111", "PT", "paciente")


def test_validar_documento_fiscal_br_cpf_valido():
    validar_documento_fiscal("529.982.247-25", "BR", "paciente")


def test_validar_documento_fiscal_br_cpf_invalido():
    with pytest.raises(ValueError, match="CPF inválido"):
        validar_documento_fiscal("111.111.111-11", "BR", "paciente")


def test_validar_documento_fiscal_br_cnpj_valido():
    validar_documento_fiscal("11.222.333/0001-81", "BR", "clinica")


def test_validar_documento_fiscal_br_cnpj_invalido():
    with pytest.raises(ValueError, match="CNPJ inválido"):
        validar_documento_fiscal("11.222.333/0001-82", "BR", "clinica")


def test_validar_documento_fiscal_none_noop():
    # None/empty should be a no-op
    validar_documento_fiscal(None, "PT", "paciente")
    validar_documento_fiscal("", "BR", "clinica")


# ─── Agent locale: system prompt language ─────────────────────────────────────

def test_triage_agent_pt_usa_prompt_pt():
    from app.agents.triage_agent import TriageAgent
    agent = TriageAgent(pais="PT")
    assert "112" in agent.system_prompt, "PT triage prompt must reference 112 (PT emergency)"
    assert "SAMU" not in agent.system_prompt, "PT triage prompt must not mention SAMU (BR)"


def test_triage_agent_br_usa_prompt_br():
    from app.agents.triage_agent import TriageAgent
    agent = TriageAgent(pais="BR")
    assert "SAMU" in agent.system_prompt, "BR triage prompt must reference SAMU"
    assert "112" not in agent.system_prompt, "BR triage prompt must not mention 112 (PT)"


def test_whatsapp_agent_pt_usa_prompt_pt():
    from app.agents.whatsapp_agent import WhatsAppAgent
    db = MagicMock()
    agent = WhatsAppAgent(paciente={}, clinica_id="x", db=db, pais="PT")
    assert "RGPD" in agent.system_prompt


def test_whatsapp_agent_br_usa_prompt_br():
    from app.agents.whatsapp_agent import WhatsAppAgent
    db = MagicMock()
    agent = WhatsAppAgent(paciente={}, clinica_id="x", db=db, pais="BR")
    assert "LGPD" in agent.system_prompt
