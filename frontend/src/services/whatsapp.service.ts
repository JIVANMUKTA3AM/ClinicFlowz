/**
 * whatsapp.service.ts
 * WhatsApp connection management + conversation timeline.
 *
 * Architecture note:
 *   Actual WhatsApp message delivery is handled server-side by the Evolution API
 *   integration. The frontend creates outbound timeline entries (tipo=whatsapp,
 *   direcao=saida) which are recorded in the patient history; the backend agent
 *   handles the actual send via webhook processing.
 *
 * UI-ready enrichments:
 *   - `InteracaoUI` adds `hora_label`, `data_label`, `is_entrada`, `is_bubble`
 *   - `ConversaUI` groups interações by patient with last-message preview
 */

import { format, parseISO, isToday, isYesterday } from "date-fns"
import { ptBR, pt } from "date-fns/locale"
import http from "./http"
import { handleError } from "./errors"
import type { Interacao, InteracaoTipo, Paciente } from "../types"

// ─── DTOs ─────────────────────────────────────────────────────────────────────

export interface RegistarConexaoDTO {
  instance_name: string
  phone_number: string
}

export interface EnviarMensagemDTO {
  paciente_id: string
  conteudo: string
  tipo?: Extract<InteracaoTipo, "whatsapp" | "sms" | "nota">
}

// ─── Raw API shapes ───────────────────────────────────────────────────────────

interface WhatsAppConnection {
  id: string
  clinica_id: string
  instance_name: string
  phone_number: string
  ativo: boolean
  created_at: string
}

// ─── UI-ready shapes ──────────────────────────────────────────────────────────

export interface InteracaoUI extends Interacao {
  /** "09:30" */
  hora_label: string
  /** "Hoje" | "Ontem" | "24 Mar" */
  data_label: string
  /** Full datetime for tooltips */
  datetime_label: string
  /** true for direcao === "entrada" */
  is_entrada: boolean
  /** true for whatsapp / sms — renders as chat bubble */
  is_bubble: boolean
  /** Day key for grouping ("YYYY-MM-DD") */
  day_key: string
}

export interface ConversaUI {
  paciente: Paciente
  ultima_mensagem: InteracaoUI | null
  total_mensagens: number
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const BUBBLE_TIPOS: InteracaoTipo[] = ["whatsapp", "sms"]

function dataLabel(iso: string, dateFnsLocale: typeof ptBR): string {
  const d = parseISO(iso)
  if (isToday(d))     return "Hoje"
  if (isYesterday(d)) return "Ontem"
  return format(d, "d MMM", { locale: dateFnsLocale })
}

function enrichInteracao(i: Interacao, pais: string = "PT"): InteracaoUI {
  const dateFnsLocale = pais === "PT" ? pt : ptBR
  const dt = parseISO(i.created_at)
  return {
    ...i,
    hora_label:     format(dt, "HH:mm"),
    data_label:     dataLabel(i.created_at, dateFnsLocale),
    datetime_label: format(dt, "d MMM yyyy, HH:mm", { locale: dateFnsLocale }),
    is_entrada:     i.direcao === "entrada",
    is_bubble:      BUBBLE_TIPOS.includes(i.tipo),
    day_key:        i.created_at.slice(0, 10),
  }
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const whatsappService = {
  // ── Connections ─────────────────────────────────────────────────────────────

  /** List active WhatsApp instances for this clinic. */
  async listarConexoes(): Promise<WhatsAppConnection[]> {
    try {
      const res = await http.get<WhatsAppConnection[]>("/api/v1/whatsapp/connections")
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  /** Register a new Evolution API instance for this clinic. */
  async registarConexao(dto: RegistarConexaoDTO): Promise<WhatsAppConnection> {
    try {
      const res = await http.post<WhatsAppConnection>("/api/v1/whatsapp/connections", dto)
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  /** Soft-deactivate a connection (messages from that instance will be dropped). */
  async desativarConexao(id: string): Promise<void> {
    try {
      await http.delete(`/api/v1/whatsapp/connections/${id}`)
    } catch (e) {
      handleError(e)
    }
  },

  // ── Timeline / messages ──────────────────────────────────────────────────────

  /**
   * Full interaction history for a patient.
   * Returned oldest-first (API returns desc — we reverse here).
   * Adds UI-ready labels and grouping keys.
   */
  async historico(paciente_id: string, limit = 100, pais: string = "PT"): Promise<InteracaoUI[]> {
    try {
      const res = await http.get<Interacao[]>(`/api/v1/timeline/${paciente_id}`, {
        params: { limit },
      })
      return res.data.map((i) => enrichInteracao(i, pais)).reverse()   // oldest first
    } catch (e) {
      handleError(e)
    }
  },

  /**
   * Record a manual outbound message in the patient timeline.
   *
   * This creates a timeline entry (tipo=whatsapp, direcao=saida).
   * For the WhatsApp message to actually be delivered, the clinic must have
   * a configured Evolution API connection — the backend handles the send
   * via the agent pipeline when the session is active.
   */
  async enviarMensagem(dto: EnviarMensagemDTO): Promise<InteracaoUI> {
    try {
      const res = await http.post<Interacao>("/api/v1/timeline/", {
        paciente_id: dto.paciente_id,
        tipo:        dto.tipo ?? "whatsapp",
        direcao:     "saida",
        conteudo:    dto.conteudo,
        criado_por:  "recepcao",
      })
      return enrichInteracao(res.data)
    } catch (e) {
      handleError(e)
    }
  },

  /**
   * Add a manual note to the patient timeline (not a WhatsApp message).
   */
  async adicionarNota(paciente_id: string, conteudo: string): Promise<InteracaoUI> {
    try {
      const res = await http.post<Interacao>("/api/v1/timeline/", {
        paciente_id,
        tipo:       "nota",
        conteudo,
        criado_por: "recepcao",
      })
      return enrichInteracao(res.data)
    } catch (e) {
      handleError(e)
    }
  },

  /**
   * Build a conversation list from a list of patients.
   * Fetches the most recent interaction per patient in parallel (batched).
   *
   * Designed for the chat sidebar — returns sorted by latest message desc.
   */
  async conversas(pacientes: Paciente[]): Promise<ConversaUI[]> {
    if (pacientes.length === 0) return []

    const resultados = await Promise.allSettled(
      pacientes.map(async (p): Promise<ConversaUI> => {
        try {
          const res = await http.get<Interacao[]>(`/api/v1/timeline/${p.id}`, {
            params: { limit: 1 },
          })
          const raw = res.data[0] ?? null
          return {
            paciente:       p,
            ultima_mensagem: raw ? enrichInteracao(raw) : null,
            total_mensagens: res.data.length,
          }
        } catch {
          return { paciente: p, ultima_mensagem: null, total_mensagens: 0 }
        }
      }),
    )

    return resultados
      .filter((r): r is PromiseFulfilledResult<ConversaUI> => r.status === "fulfilled")
      .map((r) => r.value)
      .sort((a, b) => {
        const ta = a.ultima_mensagem?.created_at ?? ""
        const tb = b.ultima_mensagem?.created_at ?? ""
        return tb.localeCompare(ta)                    // newest first
      })
  },
}
