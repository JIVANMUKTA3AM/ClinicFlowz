/**
 * consultas.service.ts
 * Appointment CRUD + agenda-do-dia + weekly range fetch.
 *
 * UI-ready enrichments:
 *   - `hora`          "09:30"
 *   - `data_label`    "Segunda, 24 Mar"
 *   - `duracao_label` "30 min"
 *   - `valor_label`   "€ 45,00" | "—"
 *   - `paciente_nome` / `medico_nome` flattened from nested join
 */

import { format, parseISO } from "date-fns"
import { ptBR, pt } from "date-fns/locale"
import http from "./http"
import { handleError } from "./errors"
import { formatCurrency } from "../lib/locale"
import type { Consulta, ConsultaStatus, ConsultaTipo } from "../types"

// ─── DTOs ─────────────────────────────────────────────────────────────────────

export interface CriarConsultaDTO {
  paciente_id: string
  medico_id: string
  sala_id?: string
  data_hora: string                   // ISO 8601
  duracao_min?: number                // default 30
  tipo?: ConsultaTipo
  valor?: number
  forma_pagamento?: string
  observacoes?: string
}

export interface AtualizarConsultaDTO {
  status?: ConsultaStatus
  data_hora?: string
  valor?: number
  pago?: boolean
  forma_pagamento?: string
  observacoes?: string
}

export interface ListarConsultasParams {
  data_inicio?: string               // YYYY-MM-DD
  data_fim?: string
  medico_id?: string
  sala_id?: string
  status?: ConsultaStatus
  paciente_id?: string
  limit?: string
}

// ─── UI-ready shape ───────────────────────────────────────────────────────────

export interface ConsultaUI extends Consulta {
  hora: string                        // "09:30"
  data_label: string                  // "Seg, 24 Mar"
  duracao_label: string               // "30 min"
  valor_label: string                 // "€ 45,00" | "—"
  paciente_nome: string               // flattened
  medico_nome: string                 // flattened
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function enrich(c: Consulta, pais: string = "PT"): ConsultaUI {
  const dt = parseISO(c.data_hora)
  const dateFnsLocale = pais === "PT" ? pt : ptBR
  return {
    ...c,
    hora:          format(dt, "HH:mm"),
    data_label:    format(dt, "EEE, d MMM", { locale: dateFnsLocale }),
    duracao_label: `${c.duracao_min} min`,
    valor_label:   c.valor != null ? formatCurrency(c.valor, pais) : "—",
    paciente_nome: c.pacientes?.nome ?? "—",
    medico_nome:   c.medicos?.nome   ?? "—",
  }
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const consultasService = {
  /**
   * General list with date-range and other filters.
   * Used by the weekly calendar view.
   */
  async listar(params?: ListarConsultasParams, pais: string = "PT"): Promise<ConsultaUI[]> {
    try {
      const res = await http.get<Consulta[]>("/api/v1/consultas/", { params })
      return res.data.map((c) => enrich(c, pais))
    } catch (e) {
      handleError(e)
    }
  },

  /**
   * Today's appointments — optimised endpoint on the backend.
   * Returns appointments sorted by data_hora ASC.
   */
  async agendaHoje(medico_id?: string, pais: string = "PT"): Promise<ConsultaUI[]> {
    try {
      const res = await http.get<Consulta[]>("/api/v1/consultas/agenda-do-dia", {
        params: medico_id ? { medico_id } : undefined,
      })
      return res.data.map((c) => enrich(c, pais))
    } catch (e) {
      handleError(e)
    }
  },

  /** Create a new appointment. */
  async criar(dto: CriarConsultaDTO, pais: string = "PT"): Promise<ConsultaUI> {
    try {
      const res = await http.post<Consulta>("/api/v1/consultas/", {
        ...dto,
        status:      "agendada",
        pago:        false,
        duracao_min: dto.duracao_min ?? 30,
        tipo:        dto.tipo        ?? "primeira_vez",
      })
      return enrich(res.data, pais)
    } catch (e) {
      handleError(e)
    }
  },

  /** Partial update — status change, mark as paid, reschedule, etc. */
  async atualizar(id: string, dto: AtualizarConsultaDTO, pais: string = "PT"): Promise<ConsultaUI> {
    try {
      const res = await http.patch<Consulta>(`/api/v1/consultas/${id}`, dto)
      return enrich(res.data, pais)
    } catch (e) {
      handleError(e)
    }
  },

  /** Shorthand: change only the status field. */
  async mudarStatus(id: string, status: ConsultaStatus): Promise<ConsultaUI> {
    return consultasService.atualizar(id, { status })
  },

  /** Shorthand: mark as paid with optional payment method. */
  async marcarPago(id: string, forma_pagamento?: string): Promise<ConsultaUI> {
    return consultasService.atualizar(id, { pago: true, forma_pagamento })
  },
}
