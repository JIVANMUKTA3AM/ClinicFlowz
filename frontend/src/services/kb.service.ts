import http from "./http"
import { handleError } from "./errors"

// ─── Types ────────────────────────────────────────────────────────────────────

export type KbCategory = "empresa" | "contato" | "servico" | "precificacao" | "faq" | "politica"

export const KB_CATEGORY_LABELS: Record<KbCategory, string> = {
  empresa:       "Empresa",
  contato:       "Contacto",
  servico:       "Serviços",
  precificacao:  "Preços",
  faq:           "FAQ",
  politica:      "Políticas",
}

export interface KbEntity {
  id: string
  category: KbCategory
  title: string
  content: string
  metadata: Record<string, unknown>
  active: boolean
  created_at: string
  updated_at: string
}

export interface KbCreateDTO {
  category: KbCategory
  title: string
  content: string
  metadata?: Record<string, unknown>
}

export interface KbUpdateDTO {
  category?: KbCategory
  title?: string
  content?: string
  metadata?: Record<string, unknown>
  active?: boolean
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const kbService = {
  async list(category?: KbCategory): Promise<KbEntity[]> {
    try {
      const params = category ? `?category=${category}` : ""
      const res = await http.get(`/api/v1/kb/${params}`)
      return res.data as KbEntity[]
    } catch (e) {
      throw handleError(e)
    }
  },

  async create(dto: KbCreateDTO): Promise<KbEntity> {
    try {
      const res = await http.post("/api/v1/kb/", dto)
      return res.data as KbEntity
    } catch (e) {
      throw handleError(e)
    }
  },

  async update(id: string, dto: KbUpdateDTO): Promise<KbEntity> {
    try {
      const res = await http.put(`/api/v1/kb/${id}`, dto)
      return res.data as KbEntity
    } catch (e) {
      throw handleError(e)
    }
  },

  async deactivate(id: string): Promise<void> {
    try {
      await http.delete(`/api/v1/kb/${id}`)
    } catch (e) {
      throw handleError(e)
    }
  },
}
