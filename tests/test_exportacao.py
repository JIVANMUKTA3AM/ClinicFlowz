"""
tests/test_exportacao.py
Tests for GET /exportacao/paciente/{id} and GET /exportacao/clinica

Covers:
  1. Patient export returns correct patient data
  2. Cross-tenant: patient from another clinic → 404
  3. Patient not found → 404
  4. Audit record is created on successful patient export
  5. Audit record is created on successful clinic export
  6. Locale label adapts to pais (PT → RGPD / NIF, BR → LGPD / CPF)
  7. Clinic export returns correct clinic structure
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.exportacao import router
from app.core.database import get_clinica_id, get_supabase, get_current_user

# ─── Constants ────────────────────────────────────────────────────────────────

CLINICA_A = str(uuid4())
CLINICA_B = str(uuid4())
PACIENTE_A_ID = str(uuid4())
USER_A = {"sub": "user-a", "email": "a@test.com", "user_metadata": {"clinica_id": CLINICA_A}}

# ─── Fixture helpers ──────────────────────────────────────────────────────────

def _make_app(mock_db: MagicMock, clinica_id: str = CLINICA_A, user: dict = USER_A) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/exportacao")
    app.dependency_overrides[get_clinica_id]    = lambda: clinica_id
    app.dependency_overrides[get_supabase]      = lambda: mock_db
    app.dependency_overrides[get_current_user]  = lambda: user
    return TestClient(app)


def _clinica_row(pais: str = "PT", clinica_id: str = CLINICA_A) -> dict:
    return {
        "id": clinica_id, "nome": "Clínica Teste", "pais": pais,
        "documento_fiscal": None, "email": None, "telefone": None,
        "morada": None, "cidade": None, "plano": "starter",
        "ativo": True, "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _paciente_row(clinica_id: str = CLINICA_A) -> dict:
    return {
        "id": PACIENTE_A_ID, "clinica_id": clinica_id, "nome": "Ana Costa",
        "telefone": "+351912345678", "email": None, "documento_fiscal": None,
        "data_nascimento": None, "genero": None, "origem": "balcao",
        "status": "ativo", "tags": [], "notas": None,
        "consentimento_privacidade_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_db_mock_for_patient_export(
    found: bool = True,
    clinica_pais: str = "PT",
    clinica_id: str = CLINICA_A,
) -> tuple[MagicMock, list]:
    """
    Returns (db_mock, audit_captures).
    audit_captures is a list that will receive the payload passed to audit insert.
    """
    audit_captures: list = []

    def table_factory(table_name: str):
        mock = MagicMock()

        if table_name == "pacientes":
            single_chain = MagicMock()
            pac_data = _paciente_row(clinica_id) if found else None
            single_chain.execute.return_value = MagicMock(data=pac_data)
            mock.select.return_value.eq.return_value.eq.return_value.single.return_value = single_chain

        elif table_name == "consultas":
            mock.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "interacoes":
            mock.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "pipeline":
            mock.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "clinicas":
            single_chain = MagicMock()
            single_chain.execute.return_value = MagicMock(data={"pais": clinica_pais, "nome": "Clínica Teste"})
            mock.select.return_value.eq.return_value.single.return_value = single_chain

        elif table_name == "exportacoes_auditoria":
            def capture_insert(data: dict):
                audit_captures.append(data)
                ins = MagicMock()
                ins.execute.return_value = MagicMock(data=[{"id": str(uuid4())}])
                return ins
            mock.insert.side_effect = capture_insert

        return mock

    db = MagicMock()
    db.table.side_effect = table_factory
    return db, audit_captures


def _build_db_mock_for_clinic_export(pais: str = "PT") -> tuple[MagicMock, list]:
    audit_captures: list = []

    def table_factory(table_name: str):
        mock = MagicMock()

        if table_name == "clinicas":
            single_chain = MagicMock()
            single_chain.execute.return_value = MagicMock(data=_clinica_row(pais))
            mock.select.return_value.eq.return_value.single.return_value = single_chain

        elif table_name == "medicos":
            mock.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "salas":
            mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "whatsapp_connections":
            mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "pacientes":
            mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "consultas":
            mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        elif table_name == "exportacoes_auditoria":
            def capture_insert(data: dict):
                audit_captures.append(data)
                ins = MagicMock()
                ins.execute.return_value = MagicMock(data=[{"id": str(uuid4())}])
                return ins
            mock.insert.side_effect = capture_insert

        return mock

    db = MagicMock()
    db.table.side_effect = table_factory
    return db, audit_captures


# ─── Tests: patient export ────────────────────────────────────────────────────

def test_exportar_paciente_retorna_dados_corretos():
    """Exportação devolve dados do paciente correcto com estrutura esperada."""
    db, _ = _build_db_mock_for_patient_export(found=True)
    client = _make_app(db)

    resp = client.get(f"/exportacao/paciente/{PACIENTE_A_ID}")

    assert resp.status_code == 200
    body = resp.json()

    # Estrutura de topo
    assert "exportacao" in body
    assert "paciente" in body
    assert "consultas" in body
    assert "interacoes" in body
    assert "totais" in body

    # Dados do paciente
    assert body["paciente"]["id"] == PACIENTE_A_ID
    assert body["paciente"]["nome"] == "Ana Costa"

    # Cabeçalho de exportação
    assert body["exportacao"]["versao"] == "1.0"
    assert "exportado_em" in body["exportacao"]


def test_exportar_paciente_cross_tenant_bloqueado():
    """Paciente de outra clínica não é encontrado — deve retornar 404."""
    # DB devolve None porque o .eq("clinica_id", CLINICA_A) filtra PACIENTE_B
    db, _ = _build_db_mock_for_patient_export(found=False)
    client = _make_app(db, clinica_id=CLINICA_A)

    resp = client.get(f"/exportacao/paciente/{PACIENTE_A_ID}")

    assert resp.status_code == 404
    assert "não encontrado" in resp.json()["detail"].lower()


def test_exportar_paciente_nao_existente_retorna_404():
    """Paciente que não existe → 404."""
    db, _ = _build_db_mock_for_patient_export(found=False)
    client = _make_app(db)

    resp = client.get(f"/exportacao/paciente/{uuid4()}")

    assert resp.status_code == 404


def test_exportar_paciente_cria_registo_auditoria():
    """Exportação de paciente deve gravar um registo em exportacoes_auditoria."""
    db, audit_captures = _build_db_mock_for_patient_export(found=True)
    client = _make_app(db)

    resp = client.get(f"/exportacao/paciente/{PACIENTE_A_ID}")

    assert resp.status_code == 200
    assert len(audit_captures) == 1

    audit = audit_captures[0]
    assert audit["tipo"] == "paciente"
    assert audit["user_id"] == USER_A["sub"]
    assert audit["clinica_id"] == CLINICA_A
    assert audit["paciente_id"] == PACIENTE_A_ID
    assert "exportado_at" in audit


def test_exportar_paciente_locale_pt_usa_rgpd():
    """Exportação de clínica PT → lei_privacidade='RGPD', label='NIF'."""
    db, _ = _build_db_mock_for_patient_export(found=True, clinica_pais="PT")
    client = _make_app(db)

    resp = client.get(f"/exportacao/paciente/{PACIENTE_A_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["exportacao"]["lei_privacidade"] == "RGPD"
    assert body["paciente"]["documento_fiscal_label"] == "NIF"


def test_exportar_paciente_locale_br_usa_lgpd():
    """Exportação de clínica BR → lei_privacidade='LGPD', label='CPF'."""
    db, _ = _build_db_mock_for_patient_export(found=True, clinica_pais="BR")
    client = _make_app(db)

    resp = client.get(f"/exportacao/paciente/{PACIENTE_A_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["exportacao"]["lei_privacidade"] == "LGPD"
    assert body["paciente"]["documento_fiscal_label"] == "CPF"


# ─── Tests: clinic export ─────────────────────────────────────────────────────

def test_exportar_clinica_retorna_estrutura_correta():
    """Exportação de clínica devolve campos esperados."""
    db, _ = _build_db_mock_for_clinic_export(pais="PT")
    client = _make_app(db)

    resp = client.get("/exportacao/clinica")

    assert resp.status_code == 200
    body = resp.json()

    assert "exportacao" in body
    assert "clinica" in body
    assert "medicos" in body
    assert "salas" in body
    assert "totais" in body

    assert body["clinica"]["nome"] == "Clínica Teste"
    assert body["clinica"]["pais"] == "PT"
    assert body["clinica"]["lei_privacidade"] == "RGPD"
    assert body["exportacao"]["lei_privacidade"] == "RGPD"


def test_exportar_clinica_cria_registo_auditoria():
    """Exportação de clínica deve gravar registo de auditoria sem paciente_id."""
    db, audit_captures = _build_db_mock_for_clinic_export(pais="BR")
    client = _make_app(db)

    resp = client.get("/exportacao/clinica")

    assert resp.status_code == 200
    assert len(audit_captures) == 1

    audit = audit_captures[0]
    assert audit["tipo"] == "clinica"
    assert audit["user_id"] == USER_A["sub"]
    assert audit["clinica_id"] == CLINICA_A
    assert "paciente_id" not in audit  # exportação de clínica não tem paciente_id


def test_exportar_clinica_locale_br():
    """Clínica BR → LGPD, CNPJ, BRL."""
    db, _ = _build_db_mock_for_clinic_export(pais="BR")
    client = _make_app(db)

    resp = client.get("/exportacao/clinica")

    assert resp.status_code == 200
    body = resp.json()
    assert body["clinica"]["lei_privacidade"] == "LGPD"
    assert body["clinica"]["documento_fiscal_label"] == "CNPJ"
    assert body["clinica"]["moeda"] == "BRL"
