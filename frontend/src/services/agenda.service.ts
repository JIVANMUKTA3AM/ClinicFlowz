/**
 * agenda.service.ts
 * Weekly schedule + clinic KPIs.
 *
 * `kpis(pais)` accepts the clinic's country so currency is formatted correctly.
 */

import http from "./http"
import { handleError } from "./errors"
import { formatCurrency } from "../lib/locale"
import type { Consulta } from "../types"

// ─── Raw API response ─────────────────────────────────────────────────────────

interface KpisRaw {
  mes: string
  consultas_total: number
  taxa_falta_pct: number
  receita_realizada_eur: number
  pacientes_novos: number
  leads_pipeline: number
}

interface AgendaSemanaRaw {
  inicio: string
  fim: string
  consultas: Consulta[]
}

// ─── UI-ready shapes ──────────────────────────────────────────────────────────

export interface KpisUI {
  mes: string
  consultas_total: number
  taxa_falta_pct: number
  receita_realizada_eur: number
  pacientes_novos: number
  leads_pipeline: number
  taxa_comparecimento_pct: number
  receita_label: string
}

export interface AgendaSemanaUI {
  inicio: string
  fim: string
  porDia: Record<string, Consulta[]>
  total: number
}

export interface SlotUI {
  hora: string
  hora_num: number
  disponivel: boolean
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function enrichKpis(raw: KpisRaw, pais: string): KpisUI {
  return {
    ...raw,
    taxa_comparecimento_pct: Math.max(0, 100 - raw.taxa_falta_pct),
    receita_label: formatCurrency(raw.receita_realizada_eur, pais),
  }
}

function groupByDay(consultas: Consulta[]): Record<string, Consulta[]> {
  return consultas.reduce<Record<string, Consulta[]>>((acc, c) => {
    const day = c.data_hora.slice(0, 10)
    if (!acc[day]) acc[day] = []
    acc[day].push(c)
    return acc
  }, {})
}

function horaToNum(h: string): number {
  const [hh, mm] = h.split(":").map(Number)
  return hh * 100 + mm
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const agendaService = {
  async semana(inicio?: string, medico_id?: string): Promise<AgendaSemanaUI> {
    try {
      const params: Record<string, string> = {}
      if (inicio)    params.inicio    = inicio
      if (medico_id) params.medico_id = medico_id

      const res = await http.get<AgendaSemanaRaw>("/api/v1/agenda/semana", { params })
      const { consultas, ...rest } = res.data
      return { ...rest, porDia: groupByDay(consultas), total: consultas.length }
    } catch (e) {
      handleError(e)
    }
  },

  async kpis(pais: string = "PT"): Promise<KpisUI> {
    try {
      const res = await http.get<KpisRaw>("/api/v1/agenda/kpis")
      return enrichKpis(res.data, pais)
    } catch (e) {
      handleError(e)
    }
  },

  async disponibilidade(medico_id: string, data: string): Promise<SlotUI[]> {
    try {
      const res = await http.get<{ data: string; medico_id: string; slots_disponiveis: string[] }>(
        `/api/v1/medicos/${medico_id}/disponibilidade`,
        { params: { data } },
      )
      return res.data.slots_disponiveis
        .map((hora) => ({ hora, hora_num: horaToNum(hora), disponivel: true }))
        .sort((a, b) => a.hora_num - b.hora_num)
    } catch (e) {
      handleError(e)
    }
  },
}
