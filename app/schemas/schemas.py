from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
from uuid import UUID

# ─── Enums ────────────────────────────────────────────────────────────────────

class PacienteStatus(str, Enum):
    lead      = "lead"
    ativo     = "ativo"
    inativo   = "inativo"
    arquivado = "arquivado"

class PacienteOrigem(str, Enum):
    whatsapp  = "whatsapp"
    site      = "site"
    indicacao = "indicacao"
    balcao    = "balcao"

class ConsultaStatus(str, Enum):
    agendada   = "agendada"
    confirmada = "confirmada"
    realizada  = "realizada"
    falta      = "falta"
    cancelada  = "cancelada"

class ConsultaTipo(str, Enum):
    primeira_vez = "primeira_vez"
    retorno      = "retorno"
    urgencia     = "urgencia"
    avaliacao    = "avaliacao"

class PipelineEtapa(str, Enum):
    lead             = "lead"
    agendou          = "agendou"
    compareceu       = "compareceu"
    orcamento        = "orcamento"
    tratamento_ativo = "tratamento_ativo"
    concluido        = "concluido"

class InteracaoTipo(str, Enum):
    whatsapp = "whatsapp"
    sms      = "sms"
    email    = "email"
    ligacao  = "ligacao"
    nota     = "nota"
    lembrete = "lembrete"
    consulta = "consulta"

class InteracaoDirecao(str, Enum):
    entrada = "entrada"
    saida   = "saida"

# ─── Paciente ─────────────────────────────────────────────────────────────────

class PacienteBase(BaseModel):
    nome: str
    telefone: str
    email: Optional[EmailStr] = None
    documento_fiscal: Optional[str] = None
    data_nascimento: Optional[date] = None
    genero: Optional[str] = None
    origem: PacienteOrigem = PacienteOrigem.balcao
    status: PacienteStatus = PacienteStatus.lead
    tags: List[str] = []
    notas: Optional[str] = None

class PacienteCreate(PacienteBase):
    consentimento_privacidade: bool = Field(
        ..., description="Consentimento obrigatório por lei (RGPD/LGPD)"
    )

class PacienteUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[EmailStr] = None
    status: Optional[PacienteStatus] = None
    tags: Optional[List[str]] = None
    notas: Optional[str] = None

class PacienteOut(PacienteBase):
    id: UUID
    clinica_id: UUID
    consentimento_privacidade_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ─── Médico ───────────────────────────────────────────────────────────────────

class MedicoBase(BaseModel):
    nome: str
    especialidade: str
    cedula: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    comissao_pct: float = 0.0
    horarios_disponiveis: Optional[dict] = None  # {seg: ["09:00","09:30",...], ...}

class MedicoCreate(MedicoBase):
    pass

class MedicoOut(MedicoBase):
    id: UUID
    clinica_id: UUID
    ativo: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ─── Sala ─────────────────────────────────────────────────────────────────────

class SalaBase(BaseModel):
    nome: str
    descricao: Optional[str] = None

class SalaCreate(SalaBase):
    pass

class SalaUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None

class SalaOut(SalaBase):
    id: UUID
    clinica_id: UUID
    ativa: bool

    class Config:
        from_attributes = True

# ─── Consulta ─────────────────────────────────────────────────────────────────

class ConsultaBase(BaseModel):
    paciente_id: UUID
    medico_id: UUID
    sala_id: Optional[UUID] = None
    data_hora: datetime
    duracao_min: int = 30
    tipo: ConsultaTipo = ConsultaTipo.primeira_vez
    status: ConsultaStatus = ConsultaStatus.agendada
    valor: Optional[float] = None
    forma_pagamento: Optional[str] = None
    pago: bool = False
    observacoes: Optional[str] = None

class ConsultaCreate(ConsultaBase):
    pass

class ConsultaUpdate(BaseModel):
    status: Optional[ConsultaStatus] = None
    data_hora: Optional[datetime] = None
    valor: Optional[float] = None
    pago: Optional[bool] = None
    observacoes: Optional[str] = None

class ConsultaOut(ConsultaBase):
    id: UUID
    clinica_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# ─── Pipeline ─────────────────────────────────────────────────────────────────

class PipelineBase(BaseModel):
    paciente_id: UUID
    etapa: PipelineEtapa = PipelineEtapa.lead
    valor_estimado: Optional[float] = None
    observacoes: Optional[str] = None

class PipelineUpdate(BaseModel):
    etapa: PipelineEtapa
    valor_estimado: Optional[float] = None
    observacoes: Optional[str] = None

class PipelineOut(PipelineBase):
    id: UUID
    clinica_id: UUID
    etapa_updated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

# ─── Interação / Timeline ─────────────────────────────────────────────────────

class InteracaoBase(BaseModel):
    paciente_id: UUID
    tipo: InteracaoTipo
    direcao: Optional[InteracaoDirecao] = None
    conteudo: str
    criado_por: str = "sistema"  # agente_ia | recepcao | sistema

class InteracaoCreate(InteracaoBase):
    pass

class InteracaoOut(InteracaoBase):
    id: UUID
    clinica_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# ─── WhatsApp Connections ─────────────────────────────────────────────────────

class WhatsAppConnectionCreate(BaseModel):
    instance_name: str = Field(..., description="Nome da sessão Waha (único por tenant)")
    phone_number: str  = Field(..., description="Número E.164 associado, ex: +351912345678")

class WhatsAppConnectionOut(BaseModel):
    id: UUID
    clinica_id: UUID
    instance_name: str
    phone_number: str
    ativo: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ─── Clínica ──────────────────────────────────────────────────────────────────

class ClinicaOut(BaseModel):
    id: UUID
    nome: str
    documento_fiscal: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    morada: Optional[str] = None
    cidade: Optional[str] = None
    pais: str = "PT"
    plano: str = "starter"
    ativo: bool = True
    created_at: datetime

    class Config:
        from_attributes = True

# ─── Retention ────────────────────────────────────────────────────────────────

class RetentionRunRequest(BaseModel):
    campanha: str = Field(
        ...,
        description=(
            "POST_CONSULTATION | CHECKUP_REMINDER | REACTIVATION | INCOMPLETE_TREATMENT"
        ),
    )
    paciente_id: Optional[UUID] = Field(
        None,
        description="Alvo específico. Se omitido, a clínica descobre pacientes elegíveis automaticamente.",
    )
    limite: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Máximo de pacientes processados em modo batch.",
    )

class RetentionResultItem(BaseModel):
    paciente_id: str
    paciente_nome: str
    campanha: str
    actions_taken: List[str]
    message_preview: str
    summary: str
    sucesso: bool
    erro: Optional[str] = None

class RetentionRunResponse(BaseModel):
    total_processados: int
    total_sucesso: int
    total_falha: int
    resultados: List[RetentionResultItem]

# ─── WhatsApp Webhook ─────────────────────────────────────────────────────────

class WhatsAppMessage(BaseModel):
    instance: str
    data: dict  # payload bruto do Waha
