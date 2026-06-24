// ─── Enums (mirror backend) ────────────────────────────────────────────────

export type PacienteStatus = "lead" | "ativo" | "inativo" | "arquivado"
export type PacienteOrigem = "whatsapp" | "site" | "indicacao" | "balcao"
export type ConsultaStatus = "agendada" | "confirmada" | "realizada" | "falta" | "cancelada"
export type ConsultaTipo   = "primeira_vez" | "retorno" | "urgencia" | "avaliacao"
export type PipelineEtapa  = "lead" | "agendou" | "compareceu" | "orcamento" | "tratamento_ativo" | "concluido"
export type InteracaoTipo  = "whatsapp" | "sms" | "email" | "ligacao" | "nota" | "lembrete" | "consulta"
export type InteracaoDirecao = "entrada" | "saida"
export type Pais = "PT" | "BR"

// ─── Entities ──────────────────────────────────────────────────────────────

export interface Paciente {
  id: string
  clinica_id: string
  nome: string
  telefone: string
  email?: string
  documento_fiscal?: string
  data_nascimento?: string
  genero?: string
  origem: PacienteOrigem
  status: PacienteStatus
  tags: string[]
  notas?: string
  consentimento_privacidade_at?: string
  created_at: string
  updated_at: string
}

export interface Medico {
  id: string
  clinica_id: string
  nome: string
  especialidade: string
  cedula?: string
  email?: string
  telefone?: string
  comissao_pct: number
  horarios_disponiveis?: Record<string, string[]>
  ativo: boolean
  created_at: string
}

export interface Sala {
  id: string
  clinica_id: string
  nome: string
  descricao?: string
  ativa: boolean
}

export interface Consulta {
  id: string
  clinica_id: string
  paciente_id: string
  medico_id: string
  sala_id?: string
  data_hora: string
  duracao_min: number
  tipo: ConsultaTipo
  status: ConsultaStatus
  valor?: number
  forma_pagamento?: string
  pago: boolean
  observacoes?: string
  created_at: string
  // joined
  pacientes?: { nome: string; telefone: string }
  medicos?: { nome: string; especialidade: string }
}

export interface PipelineEntry {
  id: string
  clinica_id: string
  paciente_id: string
  etapa: PipelineEtapa
  valor_estimado?: number
  observacoes?: string
  etapa_updated_at: string
  created_at: string
}

export interface Interacao {
  id: string
  clinica_id: string
  paciente_id: string
  tipo: InteracaoTipo
  direcao?: InteracaoDirecao
  conteudo: string
  criado_por: string
  created_at: string
}

// ─── Agenda / KPIs ─────────────────────────────────────────────────────────

export interface AgendaSlot {
  hora: string
  medico_id: string
  medico_nome: string
  disponivel: boolean
  consulta_id?: string
}

export interface AgendaSemana {
  [isoDate: string]: AgendaSlot[]
}

export interface KpisData {
  consultas_hoje: number
  consultas_semana: number
  novos_pacientes_mes: number
  taxa_ocupacao_pct: number
  receita_mes: number
  faltas_mes: number
}

// ─── Financeiro ────────────────────────────────────────────────────────────

export interface ReceitaPorMedico {
  medico_id: string
  medico_nome: string
  especialidade: string
  total_consultas: number
  receita_total: number
  receita_paga: number
  receita_pendente: number
  ticket_medio: number
}

export interface ReceitaPorPeriodo {
  periodo: string
  total_consultas: number
  receita_total: number
  receita_paga: number
}

export interface ResumoFinanceiro {
  periodo_inicio: string
  periodo_fim: string
  receita_total: number
  receita_paga: number
  receita_pendente: number
  total_consultas: number
  consultas_pagas: number
  consultas_pendentes: number
  ticket_medio: number
  taxa_inadimplencia_pct: number
  por_medico: ReceitaPorMedico[]
  por_periodo: ReceitaPorPeriodo[]
}

export interface ComissaoPorMedico {
  medico_id: string
  medico_nome: string
  especialidade: string
  comissao_pct: number
  consultas_realizadas: number
  receita_base: number
  comissao_valor: number
}

export interface ComissoesResponse {
  periodo_inicio: string
  periodo_fim: string
  total_comissoes: number
  comissoes: ComissaoPorMedico[]
}

// ─── Pipeline funil ────────────────────────────────────────────────────────

export interface FunilEtapa {
  etapa: PipelineEtapa
  total: number
  valor_total?: number
}

// ─── Auth ──────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  clinica_id: string
  nome?: string
  pais: Pais
}

// ─── API pagination ────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  page_size: number
}
