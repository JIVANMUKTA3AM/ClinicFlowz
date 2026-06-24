import http from "./http"
import { handleError } from "./errors"

// ─── Types ────────────────────────────────────────────────────────────────────

export type TipoIntegracao = "whatsapp" | "kommo"
export type StatusIntegracao = "conectado" | "desconectado" | "erro"

export interface Integracao {
  id: string
  tipo: TipoIntegracao
  config: Record<string, string>
  ativo: boolean
  status: StatusIntegracao
  tem_credencial: boolean   // credencial NUNCA devolvida pelo backend
  created_at: string
  updated_at: string
}

export interface TestarResult {
  tipo: TipoIntegracao
  status: StatusIntegracao
  ok: boolean
  detalhe?: string
}

// ─── DTOs de entrada ──────────────────────────────────────────────────────────

export interface UpsertIntegracaoDTO {
  tipo: TipoIntegracao
  credenciais?: string        // só envia se o utilizador digitou um novo token
  config: Record<string, string>
  ativo?: boolean
}

export interface AtualizarIntegracaoDTO {
  credenciais?: string
  config?: Record<string, string>
  ativo?: boolean
}

// ─── Service ──────────────────────────────────────────────────────────────────

export interface QRResult {
  qr_code: string      // data URL base64 da imagem PNG
  session: string
  instrucao: string
}

export interface SessaoStatus {
  waha_status: string  // STOPPED | STARTING | SCAN_QR_CODE | WORKING | FAILED
  conectado: boolean
  telefone?: string    // "5511999999999@c.us" quando conectado
  nome?: string
  detalhe?: string
}

export const integracoesService = {
  async listar(): Promise<Integracao[]> {
    try {
      const res = await http.get<Integracao[]>("/api/v1/integracoes/")
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  async salvar(dto: UpsertIntegracaoDTO): Promise<Integracao> {
    try {
      const res = await http.post<Integracao>("/api/v1/integracoes/", dto)
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  async atualizar(tipo: TipoIntegracao, dto: AtualizarIntegracaoDTO): Promise<Integracao> {
    try {
      const res = await http.patch<Integracao>(`/api/v1/integracoes/${tipo}`, dto)
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  async remover(tipo: TipoIntegracao): Promise<void> {
    try {
      await http.delete(`/api/v1/integracoes/${tipo}`)
    } catch (e) {
      handleError(e)
    }
  },

  async testar(tipo: TipoIntegracao): Promise<TestarResult> {
    try {
      const res = await http.post<TestarResult>(`/api/v1/integracoes/${tipo}/testar`, {})
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  async conectarQR(): Promise<QRResult> {
    try {
      const res = await http.post<QRResult>("/api/v1/integracoes/whatsapp/conectar", {})
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  async statusSessao(): Promise<SessaoStatus> {
    try {
      const res = await http.get<SessaoStatus>("/api/v1/integracoes/whatsapp/status-sessao")
      return res.data
    } catch (e) {
      handleError(e)
    }
  },
}
