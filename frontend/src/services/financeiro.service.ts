import http from "./http"
import { handleError } from "./errors"
import type { ResumoFinanceiro, ComissoesResponse } from "../types"

export interface ResumoParams {
  data_inicio?: string
  data_fim?: string
  agrupar_por?: "dia" | "semana" | "mes"
}

export interface ComissoesParams {
  data_inicio?: string
  data_fim?: string
  medico_id?: string
}

export const financeiroService = {
  async resumo(params?: ResumoParams): Promise<ResumoFinanceiro> {
    try {
      const res = await http.get<ResumoFinanceiro>("/api/v1/financeiro/resumo", { params })
      return res.data
    } catch (e) { handleError(e) }
  },

  async comissoes(params?: ComissoesParams): Promise<ComissoesResponse> {
    try {
      const res = await http.get<ComissoesResponse>("/api/v1/financeiro/comissoes", { params })
      return res.data
    } catch (e) { handleError(e) }
  },
}
