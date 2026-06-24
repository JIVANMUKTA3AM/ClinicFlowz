import http from "./http"
import type { Pais } from "../types"

export interface CriarClinicaDTO {
  pais: Pais
  clinica_nome: string
  clinica_documento_fiscal?: string
  clinica_telefone?: string
  clinica_email?: string
  clinica_morada?: string
  clinica_cidade?: string
}

export const onboardingService = {
  criarClinica: (data: CriarClinicaDTO) =>
    http.post<{ clinica_id: string }>("/api/v1/onboarding", data).then((r) => r.data),
}
