"""
tests/test_tenant_isolation.py
Verifies multi-tenant isolation fixes:
  - medicos.py GET /{id}/disponibilidade: cross-tenant medico_id → 404
  - consultas.py POST /: cross-tenant paciente_id / medico_id / sala_id → 422
"""

from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_clinica_id, get_supabase

CLINICA_A = str(uuid4())


# ─── ChainProxy ───────────────────────────────────────────────────────────────

class ChainProxy:
    """
    Universal Supabase query-builder stub.

    Returns `self` for every chained attribute access or call.
    `.execute()` returns a MagicMock with .data and .count set to the
    values given at construction.

    Handles arbitrary chains like:
        .select().eq().eq().single().execute()
        .select().eq().gte().lte().not_.eq().execute()
    """
    def __init__(self, data, count: int | None = None):
        self._data  = data
        self._count = count if count is not None else (len(data) if data else 0)

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        return self          # any attribute access returns self

    def __call__(self, *args, **kwargs):
        return self          # any call on self returns self

    def execute(self):
        result       = MagicMock()
        result.data  = self._data
        result.count = self._count
        return result


# ─── Routing helper ───────────────────────────────────────────────────────────

def _db_router(routes: dict[str, ChainProxy]) -> MagicMock:
    """
    Returns a db mock whose .table(name) side_effect routes to the
    matching ChainProxy.  Unknown table names get an empty ChainProxy.
    """
    default = ChainProxy(data=[])
    db = MagicMock()
    db.table.side_effect = lambda name: routes.get(name, default)
    return db


# ─── medicos.py — GET /{medico_id}/disponibilidade ───────────────────────────

def _medico_client(db) -> TestClient:
    from app.api.v1.endpoints.medicos import router
    app = FastAPI()
    app.include_router(router, prefix="/medicos")
    app.dependency_overrides[get_clinica_id] = lambda: CLINICA_A
    app.dependency_overrides[get_supabase]   = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_disponibilidade_medico_outro_tenant_retorna_404():
    """
    Clinic A requests availability of a doctor that belongs to Clinic B.
    After the fix, the medicos query includes .eq("clinica_id", CLINICA_A),
    so no row is returned and the endpoint must respond 404 — not 200,
    and not 403 (which would reveal the resource exists elsewhere).
    """
    medico_b_id = str(uuid4())

    # medicos query returns None → doctor not found in CLINICA_A
    db = _db_router({"medicos": ChainProxy(data=None)})

    resp = _medico_client(db).get(
        f"/medicos/{medico_b_id}/disponibilidade",
        params={"data": "2026-06-19"},   # Friday
    )

    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


def test_disponibilidade_medico_mesmo_tenant_retorna_200():
    """
    Sanity check: the tenant filter must not break the normal path.
    Clinic A's own doctor → 200 with available slots.
    """
    medico_a_id = str(uuid4())

    db = _db_router({
        "medicos":   ChainProxy(data={"horarios_disponiveis": {"sex": ["09:00", "09:30"]}}),
        "consultas": ChainProxy(data=[]),   # no occupied slots
    })

    resp = _medico_client(db).get(
        f"/medicos/{medico_a_id}/disponibilidade",
        params={"data": "2026-06-19"},
    )

    assert resp.status_code == 200
    assert resp.json()["slots_disponiveis"] == ["09:00", "09:30"]


# ─── consultas.py — POST / ────────────────────────────────────────────────────

CONSULTA_BASE = {
    "paciente_id": str(uuid4()),
    "medico_id":   str(uuid4()),
    "data_hora":   "2026-06-25T09:00:00",
    "duracao_min": 30,
    "tipo":        "primeira_vez",
    "status":      "agendada",
    "pago":        False,
}


def _consultas_client(db) -> TestClient:
    from app.api.v1.endpoints.consultas import router
    app = FastAPI()
    app.include_router(router, prefix="/consultas")
    app.dependency_overrides[get_clinica_id] = lambda: CLINICA_A
    app.dependency_overrides[get_supabase]   = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_criar_consulta_paciente_outro_tenant_retorna_422():
    """
    Clinic A submits a paciente_id that belongs to Clinic B.
    The validation SELECT returns [], so the endpoint must reject with 422
    before any INSERT reaches the database.
    """
    # pacientes query returns empty → patient not in CLINICA_A
    db = _db_router({"pacientes": ChainProxy(data=[])})

    resp = _consultas_client(db).post(
        "/consultas/",
        json={**CONSULTA_BASE, "paciente_id": str(uuid4())},
    )

    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    assert "paciente" in resp.json()["detail"].lower()


def test_criar_consulta_medico_outro_tenant_retorna_422():
    """
    Clinic A submits a medico_id that belongs to Clinic B.
    The paciente check passes (own clinic); the medico check fails → 422.
    """
    valid_paciente = [{"id": CONSULTA_BASE["paciente_id"]}]

    db = _db_router({
        "pacientes": ChainProxy(data=valid_paciente),
        "medicos":   ChainProxy(data=[]),   # medico not in CLINICA_A
    })

    resp = _consultas_client(db).post(
        "/consultas/",
        json={**CONSULTA_BASE, "medico_id": str(uuid4())},
    )

    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    assert "médico" in resp.json()["detail"].lower()


def test_criar_consulta_sala_outro_tenant_retorna_422():
    """
    Clinic A submits a sala_id that belongs to Clinic B.
    Both paciente and medico pass; sala check fails → 422.
    """
    valid_paciente = [{"id": CONSULTA_BASE["paciente_id"]}]
    valid_medico   = [{"id": CONSULTA_BASE["medico_id"]}]

    db = _db_router({
        "pacientes": ChainProxy(data=valid_paciente),
        "medicos":   ChainProxy(data=valid_medico),
        "salas":     ChainProxy(data=[]),   # sala not in CLINICA_A
    })

    resp = _consultas_client(db).post(
        "/consultas/",
        json={**CONSULTA_BASE, "sala_id": str(uuid4())},
    )

    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    assert "sala" in resp.json()["detail"].lower()
