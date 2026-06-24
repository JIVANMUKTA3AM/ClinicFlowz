/**
 * pipeline.service.ts
 * Patient conversion funnel — list, move between stages, funnel aggregates.
 *
 * `pais` is an optional parameter on functions that format currency labels.
 * Defaults to "PT" for backward compatibility.
 */

import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR, pt } from "date-fns/locale"
import http from "./http"
import { handleError } from "./errors"
import { formatCurrency } from "../lib/locale"
import type { PipelineEntry, PipelineEtapa, FunilEtapa } from "../types"

// ─── DTOs ─────────────────────────────────────────────────────────────────────

export interface AvancarEtapaDTO {
  etapa: PipelineEtapa
  valor_estimado?: number
  observacoes?: string
}

export interface ListarPipelineParams {
  etapa?: PipelineEtapa
}

// ─── UI-ready shapes ──────────────────────────────────────────────────────────

export interface PipelineEntryUI extends PipelineEntry {
  dias_na_etapa: string
  valor_label: string
  initials: string
  paciente_nome: string
  paciente_telefone: string
}

export interface FunilEtapaUI extends FunilEtapa {
  taxa_conversao_pct: number | null
  valor_label: string
}

export interface FunilUI {
  etapas: FunilEtapaUI[]
  total_pacientes: number
  valor_total_pipeline: number
  valor_total_label: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

type WithPaciente = PipelineEntry & {
  pacientes?: { nome?: string; telefone?: string }
}

function enrichEntry(e: WithPaciente, pais: string = "PT"): PipelineEntryUI {
  const palavras = (e.pacientes?.nome ?? "").trim().split(/\s+/)
  const initials = palavras.length > 1
    ? `${palavras[0][0]}${palavras[palavras.length - 1][0]}`.toUpperCase()
    : (palavras[0]?.[0] ?? "?").toUpperCase()

  const dateFnsLocale = pais === "PT" ? pt : ptBR

  return {
    ...(e as PipelineEntry),
    dias_na_etapa: formatDistanceToNow(parseISO(e.etapa_updated_at), {
      addSuffix: true, locale: dateFnsLocale,
    }),
    valor_label: e.valor_estimado != null
      ? formatCurrency(e.valor_estimado, pais)
      : "—",
    initials,
    paciente_nome:     e.pacientes?.nome     ?? "—",
    paciente_telefone: e.pacientes?.telefone ?? "—",
  }
}

function enrichFunil(etapas: FunilEtapa[], pais: string = "PT"): FunilUI {
  let prev = 0
  const enriched: FunilEtapaUI[] = etapas.map((e, i) => {
    const taxa = i === 0 || prev === 0
      ? null
      : Math.round((e.total / prev) * 100)
    prev = e.total

    return {
      ...e,
      taxa_conversao_pct: taxa,
      valor_label: e.valor_total
        ? formatCurrency(e.valor_total, pais)
        : "—",
    }
  })

  const total_pacientes      = etapas.reduce((s, e) => s + e.total, 0)
  const valor_total_pipeline = etapas.reduce((s, e) => s + (e.valor_total ?? 0), 0)

  return {
    etapas: enriched,
    total_pacientes,
    valor_total_pipeline,
    valor_total_label: formatCurrency(valor_total_pipeline, pais),
  }
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const pipelineService = {
  async listar(params?: ListarPipelineParams, pais: string = "PT"): Promise<PipelineEntryUI[]> {
    try {
      const res = await http.get<WithPaciente[]>("/api/v1/pipeline/", { params })
      return res.data.map((e) => enrichEntry(e, pais))
    } catch (e) {
      handleError(e)
    }
  },

  async funil(): Promise<{ etapa: PipelineEtapa; total: number; valor_total?: number }[]> {
    try {
      const res = await http.get<{ etapa: PipelineEtapa; total: number; valor_total?: number }[]>("/api/v1/pipeline/funil")
      return res.data
    } catch (e) {
      handleError(e)
    }
  },

  async avancarEtapa(paciente_id: string, dto: AvancarEtapaDTO, pais: string = "PT"): Promise<PipelineEntryUI> {
    try {
      const res = await http.patch<WithPaciente>(`/api/v1/pipeline/${paciente_id}/etapa`, dto)
      return enrichEntry(res.data, pais)
    } catch (e) {
      handleError(e)
    }
  },
}
