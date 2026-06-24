import http from "./http"
import { handleError } from "./errors"
import type { Paciente, PacienteStatus, PacienteOrigem } from "../types"

// ─── Input DTOs ───────────────────────────────────────────────────────────────

export interface CriarPacienteDTO {
  nome: string
  telefone: string
  email?: string
  documento_fiscal?: string
  data_nascimento?: string
  genero?: string
  origem?: PacienteOrigem
  status?: PacienteStatus
  tags?: string[]
  notas?: string
  consentimento_privacidade: boolean
}

export interface AtualizarPacienteDTO {
  nome?: string
  telefone?: string
  email?: string
  status?: PacienteStatus
  tags?: string[]
  notas?: string
}

export interface ListarPacientesParams {
  q?: string
  status?: PacienteStatus
  origem?: PacienteOrigem
  page?: number
  page_size?: number
}

// ─── Output DTO (UI-ready) ────────────────────────────────────────────────────

export interface PacienteUI extends Paciente {
  nome_curto: string
  privacidade_ok: boolean
  idade?: number
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function enrich(p: Paciente): PacienteUI {
  const palavras = p.nome.trim().split(/\s+/)
  const nome_curto =
    palavras.length > 1
      ? `${palavras[0]} ${palavras[palavras.length - 1][0]}.`
      : palavras[0]

  let idade: number | undefined
  if (p.data_nascimento) {
    const nasc = new Date(p.data_nascimento)
    const hoje = new Date()
    idade = hoje.getFullYear() - nasc.getFullYear()
    const antes = hoje.getMonth() < nasc.getMonth() ||
      (hoje.getMonth() === nasc.getMonth() && hoje.getDate() < nasc.getDate())
    if (antes) idade -= 1
  }

  return { ...p, nome_curto, privacidade_ok: !!p.consentimento_privacidade_at, idade }
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const pacientesService = {
  async listar(params?: ListarPacientesParams): Promise<PacienteUI[]> {
    try {
      const res = await http.get<Paciente[]>("/api/v1/pacientes/", { params })
      return res.data.map(enrich)
    } catch (e) {
      handleError(e)
    }
  },

  async obter(id: string): Promise<PacienteUI> {
    try {
      const res = await http.get<Paciente>(`/api/v1/pacientes/${id}`)
      return enrich(res.data)
    } catch (e) {
      handleError(e)
    }
  },

  async criar(dto: CriarPacienteDTO): Promise<PacienteUI> {
    try {
      const res = await http.post<Paciente>("/api/v1/pacientes/", dto)
      return enrich(res.data)
    } catch (e) {
      handleError(e)
    }
  },

  async atualizar(id: string, dto: AtualizarPacienteDTO): Promise<PacienteUI> {
    try {
      const res = await http.patch<Paciente>(`/api/v1/pacientes/${id}`, dto)
      return enrich(res.data)
    } catch (e) {
      handleError(e)
    }
  },

  async arquivar(id: string): Promise<PacienteUI> {
    try {
      const res = await http.patch<Paciente>(`/api/v1/pacientes/${id}`, { status: "arquivado" })
      return enrich(res.data)
    } catch (e) {
      handleError(e)
    }
  },

  async mudarStatus(id: string, status: PacienteStatus): Promise<PacienteUI> {
    try {
      const res = await http.patch<Paciente>(`/api/v1/pacientes/${id}`, { status })
      return enrich(res.data)
    } catch (e) {
      handleError(e)
    }
  },
}
