import { useState, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR, pt, type Locale } from "date-fns/locale"
import { Phone, Euro, Clock, Loader2, GripVertical } from "lucide-react"
import { pipelineService } from "../services/api"
import { useAuthStore } from "../store/authStore"
import { formatCurrency } from "../lib/locale"
import type { PipelineEntry, PipelineEtapa } from "../types"

// ─── Column definitions ───────────────────────────────────────────────────────

const ETAPAS: {
  key: PipelineEtapa
  label: string
  accent: string
  header: string
  badge: string
}[] = [
  {
    key:    "lead",
    label:  "Leads",
    accent: "bg-slate-400",
    header: "border-t-slate-400",
    badge:  "bg-slate-100 text-slate-600",
  },
  {
    key:    "agendou",
    label:  "Agendou",
    accent: "bg-blue-400",
    header: "border-t-blue-400",
    badge:  "bg-blue-100 text-blue-700",
  },
  {
    key:    "compareceu",
    label:  "Compareceu",
    accent: "bg-indigo-500",
    header: "border-t-indigo-500",
    badge:  "bg-indigo-100 text-indigo-700",
  },
  {
    key:    "orcamento",
    label:  "Orçamento",
    accent: "bg-amber-400",
    header: "border-t-amber-400",
    badge:  "bg-amber-100 text-amber-700",
  },
  {
    key:    "tratamento_ativo",
    label:  "Em tratamento",
    accent: "bg-emerald-500",
    header: "border-t-emerald-500",
    badge:  "bg-emerald-100 text-emerald-700",
  },
  {
    key:    "concluido",
    label:  "Concluído",
    accent: "bg-green-600",
    header: "border-t-green-600",
    badge:  "bg-green-100 text-green-700",
  },
]

const ETAPA_KEYS = ETAPAS.map((e) => e.key)

// ─── Main page ────────────────────────────────────────────────────────────────

export function Pipeline() {
  const qc   = useQueryClient()
  const pais = useAuthStore((s) => s.user?.pais ?? "PT")
  const dateFnsLocale = pais === "PT" ? pt : ptBR

  // ── State ─────────────────────────────────────────────────────────────────
  const [dragging, setDragging] = useState<PipelineEntry | null>(null)
  const [dragOver, setDragOver] = useState<PipelineEtapa | null>(null)

  // ── Queries ───────────────────────────────────────────────────────────────

  const { data: entries = [], isLoading } = useQuery<PipelineEntry[]>({
    queryKey: ["pipeline"],
    queryFn: () => pipelineService.listar(),
    staleTime: 30_000,
  })

  const { data: funil = [] } = useQuery({
    queryKey: ["funil"],
    queryFn: pipelineService.funil,
    staleTime: 60_000,
  })

  // ── Grouped by etapa ──────────────────────────────────────────────────────

  const byEtapa = useMemo(() => {
    const map = new Map<PipelineEtapa, PipelineEntry[]>(
      ETAPA_KEYS.map((k) => [k, []]),
    )
    for (const e of entries) {
      map.get(e.etapa)?.push(e)
    }
    return map
  }, [entries])

  const funilMap = useMemo(
    () => new Map(funil.map((f) => [f.etapa, f])),
    [funil],
  )

  // ── Mutation with optimistic update ───────────────────────────────────────

  const moverEtapa = useMutation({
    mutationFn: ({ pacienteId, etapa }: { pacienteId: string; etapa: PipelineEtapa }) =>
      pipelineService.avancarEtapa(pacienteId, { etapa }),

    onMutate: async ({ pacienteId, etapa }) => {
      await qc.cancelQueries({ queryKey: ["pipeline"] })
      const prev = qc.getQueryData<PipelineEntry[]>(["pipeline"])

      qc.setQueryData<PipelineEntry[]>(["pipeline"], (old = []) =>
        old.map((e) =>
          e.paciente_id === pacienteId
            ? { ...e, etapa, etapa_updated_at: new Date().toISOString() }
            : e,
        ),
      )
      return { prev }
    },

    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["pipeline"], ctx.prev)
    },

    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["pipeline"] })
      qc.invalidateQueries({ queryKey: ["funil"] })
    },
  })

  // ── DnD handlers ──────────────────────────────────────────────────────────

  function onDragStart(entry: PipelineEntry) {
    setDragging(entry)
  }

  function onDragEnd() {
    setDragging(null)
    setDragOver(null)
  }

  function onColumnDragOver(e: React.DragEvent, etapa: PipelineEtapa) {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    setDragOver(etapa)
  }

  function onColumnDrop(e: React.DragEvent, etapa: PipelineEtapa) {
    e.preventDefault()
    if (dragging && dragging.etapa !== etapa) {
      moverEtapa.mutate({ pacienteId: dragging.paciente_id, etapa })
    }
    setDragging(null)
    setDragOver(null)
  }

  // ─────────────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 size={28} className="animate-spin text-brand-500" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">

      {/* ── Funil stats bar ──────────────────────────────────────────────── */}
      <FunilBar etapas={ETAPAS} funilMap={funilMap} total={entries.length} />

      {/* ── Kanban board ─────────────────────────────────────────────────── */}
      <div className="flex gap-3 flex-1 overflow-x-auto pb-2 pt-4 min-h-0">
        {ETAPAS.map((etapa) => {
          const cards    = byEtapa.get(etapa.key) ?? []
          const isTarget = dragOver === etapa.key
          const funilRow = funilMap.get(etapa.key)

          return (
            <div
              key={etapa.key}
              className={`flex flex-col min-w-[220px] w-[220px] rounded-2xl transition-all duration-150
                ${isTarget
                  ? "ring-2 ring-brand-400 bg-brand-50/60"
                  : "bg-surface-100/60"
                }`}
              onDragOver={(e) => onColumnDragOver(e, etapa.key)}
              onDragLeave={() => setDragOver(null)}
              onDrop={(e) => onColumnDrop(e, etapa.key)}
            >
              {/* Column header */}
              <div className={`bg-white rounded-t-2xl border border-surface-100 border-t-[3px] px-4 py-3 ${etapa.header}`}>
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-surface-700 uppercase tracking-wider">
                    {etapa.label}
                  </p>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${etapa.badge}`}>
                    {cards.length}
                  </span>
                </div>
                {funilRow?.valor_total ? (
                  <p className="text-xs text-surface-400 mt-0.5 font-mono">
                    {formatCurrency(funilRow.valor_total, pais)}
                  </p>
                ) : null}
              </div>

              {/* Drop zone + cards */}
              <div className="flex-1 overflow-y-auto px-2 py-2 space-y-2">
                {cards.map((entry) => (
                  <KanbanCard
                    key={entry.id}
                    entry={entry}
                    isDragging={dragging?.id === entry.id}
                    onDragStart={() => onDragStart(entry)}
                    onDragEnd={onDragEnd}
                    pais={pais}
                    dateFnsLocale={dateFnsLocale}
                  />
                ))}

                {/* Empty placeholder */}
                {cards.length === 0 && (
                  <div className={`flex items-center justify-center h-16 rounded-xl border-2 border-dashed transition-colors
                    ${isTarget
                      ? "border-brand-300 bg-brand-50 text-brand-400"
                      : "border-surface-200 text-surface-300"
                    }`}
                  >
                    <p className="text-xs">Arrastar aqui</p>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Funil stats bar ──────────────────────────────────────────────────────────

function FunilBar({
  etapas,
  funilMap,
  total,
}: {
  etapas: typeof ETAPAS
  funilMap: Map<PipelineEtapa, { total: number; valor_total?: number }>
  total: number
}) {
  if (total === 0) return null

  return (
    <div className="flex items-stretch gap-0 bg-white rounded-xl border border-surface-100 shadow-sm overflow-hidden">
      {etapas.map((e, i) => {
        const row   = funilMap.get(e.key)
        const count = row?.total ?? 0
        const pct   = total > 0 ? Math.round((count / total) * 100) : 0

        return (
          <div
            key={e.key}
            className={`flex-1 px-3 py-2.5 ${i < etapas.length - 1 ? "border-r border-surface-100" : ""}`}
          >
            <p className="text-[10px] text-surface-400 font-medium uppercase tracking-wider truncate">{e.label}</p>
            <div className="flex items-baseline gap-1.5 mt-0.5">
              <span className="text-base font-bold text-surface-800">{count}</span>
              <span className="text-xs text-surface-400">{pct}%</span>
            </div>
            {/* Mini progress bar */}
            <div className="mt-1.5 h-1 rounded-full bg-surface-100 overflow-hidden">
              <div
                className={`h-full rounded-full ${e.accent} transition-all duration-500`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Kanban card ──────────────────────────────────────────────────────────────

function KanbanCard({
  entry,
  isDragging,
  onDragStart,
  onDragEnd,
  pais = "PT",
  dateFnsLocale = ptBR,
}: {
  entry: PipelineEntry
  isDragging: boolean
  onDragStart: () => void
  onDragEnd: () => void
  pais?: string
  dateFnsLocale?: Locale
}) {
  const initials = (entry as unknown as { pacientes?: { nome?: string } })
    .pacientes?.nome
    ?.split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase() ?? "?"

  const pac = (entry as unknown as { pacientes?: { nome?: string; telefone?: string } }).pacientes

  const diaNaEtapa = formatDistanceToNow(parseISO(entry.etapa_updated_at), {
    addSuffix: false,
    locale: dateFnsLocale,
  })

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move"
        // Small ghost image delay trick for better UX
        setTimeout(onDragStart, 0)
      }}
      onDragEnd={onDragEnd}
      className={`bg-white rounded-xl border border-surface-100 shadow-sm p-3 cursor-grab active:cursor-grabbing
                  select-none transition-all duration-150
                  ${isDragging ? "opacity-40 scale-95 shadow-none" : "hover:shadow-md hover:-translate-y-0.5"}`}
    >
      {/* Top row: avatar + drag handle */}
      <div className="flex items-start justify-between gap-2 mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          {/* Avatar */}
          <div className="w-8 h-8 rounded-full bg-brand-100 text-brand-700 text-xs font-bold
                          flex items-center justify-center shrink-0">
            {initials}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-surface-800 leading-tight truncate">
              {pac?.nome ?? "—"}
            </p>
          </div>
        </div>
        <GripVertical size={14} className="text-surface-300 shrink-0 mt-1" />
      </div>

      {/* Phone */}
      {pac?.telefone && (
        <div className="flex items-center gap-1.5 text-xs text-surface-400 font-mono mb-1.5">
          <Phone size={10} className="shrink-0" />
          {pac.telefone}
        </div>
      )}

      {/* Valor estimado */}
      {entry.valor_estimado != null && (
        <div className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium mb-1.5">
          <Euro size={10} className="shrink-0" />
          {formatCurrency(entry.valor_estimado, pais)}
        </div>
      )}

      {/* Time in stage */}
      <div className="flex items-center gap-1.5 text-xs text-surface-300 mt-1 pt-1.5 border-t border-surface-50">
        <Clock size={10} className="shrink-0" />
        <span>há {diaNaEtapa}</span>
      </div>
    </div>
  )
}
