import http from "./http"
import { handleError } from "./errors"
import type { Sala } from "../types"

export const salasService = {
  async listar(apenas_ativas = true): Promise<Sala[]> {
    try {
      const res = await http.get<Sala[]>("/api/v1/salas/", { params: { apenas_ativas } })
      return res.data
    } catch (e) { handleError(e) }
  },

  async criar(data: { nome: string; descricao?: string }): Promise<Sala> {
    try {
      const res = await http.post<Sala>("/api/v1/salas/", data)
      return res.data
    } catch (e) { handleError(e) }
  },

  async atualizar(id: string, data: { nome?: string; descricao?: string }): Promise<Sala> {
    try {
      const res = await http.put<Sala>(`/api/v1/salas/${id}`, data)
      return res.data
    } catch (e) { handleError(e) }
  },

  async desativar(id: string): Promise<void> {
    try { await http.delete(`/api/v1/salas/${id}`) }
    catch (e) { handleError(e) }
  },
}
