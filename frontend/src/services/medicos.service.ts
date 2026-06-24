import http from "./http"
import { handleError } from "./errors"
import type { Medico } from "../types"

export interface CriarMedicoDTO {
  nome: string
  especialidade: string
  cedula?: string
  email?: string
  telefone?: string
  comissao_pct?: number
  horarios_disponiveis?: Record<string, string[]>
}

export interface AtualizarMedicoDTO extends Partial<CriarMedicoDTO> {}

export const medicosService = {
  async listar(apenas_ativos = true): Promise<Medico[]> {
    try {
      const res = await http.get<Medico[]>("/api/v1/medicos/", { params: { apenas_ativos } })
      return res.data
    } catch (e) { handleError(e) }
  },

  async criar(dto: CriarMedicoDTO): Promise<Medico> {
    try {
      const res = await http.post<Medico>("/api/v1/medicos/", dto)
      return res.data
    } catch (e) { handleError(e) }
  },

  async atualizar(id: string, dto: AtualizarMedicoDTO): Promise<Medico> {
    try {
      const res = await http.patch<Medico>(`/api/v1/medicos/${id}`, dto)
      return res.data
    } catch (e) { handleError(e) }
  },

  async desativar(id: string): Promise<void> {
    try { await http.delete(`/api/v1/medicos/${id}`) }
    catch (e) { handleError(e) }
  },

  async disponibilidade(id: string, data: string): Promise<string[]> {
    try {
      const res = await http.get<{ slots_disponiveis: string[] }>(
        `/api/v1/medicos/${id}/disponibilidade`, { params: { data } },
      )
      return res.data.slots_disponiveis
    } catch (e) { handleError(e) }
  },
}
