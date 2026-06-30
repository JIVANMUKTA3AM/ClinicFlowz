from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import (
    agenda,
    agent_versions,
    agentes,
    consultas,
    exportacao,
    financeiro,
    integracoes,
    kb,
    medicos,
    onboarding,
    pacientes,
    pipeline,
    retention,
    salas,
    sandbox,
    timeline,
    whatsapp,
)
from app.core.config import settings
from app.api.v1.endpoints.whatsapp import make_flush_callback
from app.services import message_buffer
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background jobs on startup; shut them down on exit."""
    start_scheduler()
    await message_buffer.init(settings.REDIS_URL)
    await message_buffer.recover(make_flush_callback)
    yield
    stop_scheduler()


app = FastAPI(
    title="ClinicFlowz API",
    version="1.0.0",
    description="Backend ClinicFlowz — CRM para clínicas médicas e dentárias (PT/BR)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agentes.router,         prefix="/api/v1/agents",         tags=["Agentes"])
app.include_router(agent_versions.router,  prefix="/api/v1/agent-versions",  tags=["Versões do Agente"])
app.include_router(kb.router,           prefix="/api/v1/kb",           tags=["Base de Conhecimento"])
app.include_router(sandbox.router,      prefix="/api/v1/sandbox",      tags=["Sandbox"])
app.include_router(exportacao.router,   prefix="/api/v1/exportacao",   tags=["Exportação"])
app.include_router(integracoes.router,  prefix="/api/v1/integracoes",  tags=["Integrações"])
app.include_router(onboarding.router,   prefix="/api/v1/onboarding",   tags=["Onboarding"])
app.include_router(pacientes.router,  prefix="/api/v1/pacientes",  tags=["Pacientes"])
app.include_router(consultas.router,  prefix="/api/v1/consultas",  tags=["Consultas"])
app.include_router(medicos.router,    prefix="/api/v1/medicos",    tags=["Médicos"])
app.include_router(agenda.router,     prefix="/api/v1/agenda",     tags=["Agenda"])
app.include_router(pipeline.router,   prefix="/api/v1/pipeline",   tags=["Pipeline"])
app.include_router(salas.router,      prefix="/api/v1/salas",      tags=["Salas"])
app.include_router(timeline.router,   prefix="/api/v1/timeline",   tags=["Timeline"])
app.include_router(whatsapp.router,   prefix="/api/v1/whatsapp",   tags=["WhatsApp"])
app.include_router(retention.router,  prefix="/api/v1/retention",  tags=["Retention"])
app.include_router(financeiro.router, prefix="/api/v1/financeiro", tags=["Financeiro"])


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
