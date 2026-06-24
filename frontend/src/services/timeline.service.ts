import http from "./http"
import { handleError } from "./errors"
import type { Interacao, InteracaoTipo } from "../types"

export const timelineService = {
  async paciente(id: string, limit = 100): Promise<Interacao[]> {
    try {
      const res = await http.get<Interacao[]>(`/api/v1/timeline/${id}`, { params: { limit } })
      return res.data
    } catch (e) { handleError(e) }
  },

  async criar(data: {
    paciente_id: string
    tipo: InteracaoTipo
    conteudo: string
    direcao?: "entrada" | "saida"
    criado_por?: string
  }): Promise<Interacao> {
    try {
      const res = await http.post<Interacao>("/api/v1/timeline/", {
        criado_por: "recepcao",
        ...data,
      })
      return res.data
    } catch (e) { handleError(e) }
  },
}
