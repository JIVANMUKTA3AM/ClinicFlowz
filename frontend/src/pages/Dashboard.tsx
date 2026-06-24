import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  format, subDays, parseISO, formatDistanceToNow,
  isToday,
} from "date-fns"
import { ptBR, pt, type Locale } from "date-fns/locale"
import {
  CalendarCheck2, TrendingUp, Users, HeartPulse,
  Clock, CheckCircle2, XCircle, Minus, RefreshCw,
  ArrowRight,
} from "lucide-react"
import {
  agendaService, consultasService, pipelineService, financeiroService,
} from "../services/api"
import { useAuthStore } from "../store/authStore"
import { formatCurrency } from "../lib/locale"
import type { Consulta, ConsultaStatus } from "../types"

// ─── Intervals ────────────────────────────────────────────────────────────────

const POLL_AGENDA     = 30_000
const POLL_KPIS       = 60_000
const POLL_FINANCEIRO = 120_000

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_CFG: Record<ConsultaStatus, { label: string; cls: string; Icon: typeof Clock }> = {
  agendada:   { label: "Agendada",   cls: "bg-blue-50 text-blue-700",     Icon: Clock },
  confirmada: { label: "Confirmada", cls: "bg-emerald-50 text-emerald-700", Icon: CheckCircle2 },
  realizada:  { label: "Realizada",  cls: "bg-slate-100 text-slate-600",   Icon: CheckCircle2 },
  falta:      { label: "Falta",      cls: "bg-red-50 text-red-600",        Icon: XCircle },
  cancelada:  { label: "Cancelada",  cls: "bg-orange-50 text-orange-600",  Icon: Minus },
}

const FUNIL_ETAPAS = [
  { key: "lead",             label: "Leads",         cls: "bg-slate-400" },
  { key: "agendou",          label: "Agendou",        cls: "bg-blue-400" },
  { key: "compareceu",       label: "Compareceu",     cls: "bg-indigo-500" },
  { key: "orcamento",        label: "Orçamento",      cls: "bg-amber-400" },
  { key: "tratamento_ativo", label: "Em tratamento",  cls: "bg-emerald-500" },
  { key: "concluido",        label: "Concluído",      cls: "bg-green-600" },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function pct(a: number, b: number) {
  return b > 0 ? Math.round((a / b) * 100) : 0
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function Dashboard() {
  const user        = useAuthStore((s) => s.user)
  const pais        = user?.pais ?? "PT"
  const dateFnsLocale = pais === "PT" ? pt : ptBR

  const hoje        = new Date()
  const data14Atras = format(subDays(hoje, 13), "yyyy-MM-dd")
  const dataHoje    = format(hoje, "yyyy-MM-dd")

  // ── Queries ─────────────────────────────────────────────────────────────

  const {
    data: kpis,
    dataUpdatedAt: kpisAt,
    refetch: refetchKpis,
    isFetching: fetchingKpis,
  } = useQuery({
    queryKey: ["kpis"],
    queryFn: () => agendaService.kpis(pais),
    refetchInterval: POLL_KPIS,
    staleTime: 30_000,
  })

  const { data: agendaHoje = [] } = useQuery<Consulta[]>({
    queryKey: ["agenda-hoje"],
    queryFn: () => consultasService.agendaHoje(undefined, pais),
    refetchInterval: POLL_AGENDA,
    staleTime: 0,
  })

  const { data: funilData = [] } = useQuery({
    queryKey: ["funil"],
    queryFn: pipelineService.funil,
    refetchInterval: POLL_KPIS,
    staleTime: 30_000,
  })

  const { data: financeiroData } = useQuery({
    queryKey: ["financeiro-14d", data14Atras],
    queryFn: () =>
      financeiroService.resumo({
        data_inicio: data14Atras,
        data_fim:    dataHoje,
        agrupar_por: "dia",
      }),
    refetchInterval: POLL_FINANCEIRO,
    staleTime: 60_000,
  })

  // ── Derived KPIs ─────────────────────────────────────────────────────────

  const { consultasHoje, comparecimento, pendentes } = useMemo(() => {
    const total      = agendaHoje.length
    const realizadas = agendaHoje.filter((c) => c.status === "realizada").length
    const faltas     = agendaHoje.filter((c) => c.status === "falta").length
    const confirmadas = agendaHoje.filter((c) => c.status === "confirmada").length
    const passadas   = realizadas + faltas
    const pend       = agendaHoje.filter((c) => c.status === "agendada").length

    return {
      consultasHoje:  total,
      comparecimento: passadas > 0 ? pct(realizadas, passadas) : null,
      pendentes:      pend,
    }
  }, [agendaHoje])

  // ── Bar chart data (last 14 days) ─────────────────────────────────────────

  const barData = useMemo(() => {
    const periodoMap = new Map(
      (financeiroData?.por_periodo ?? []).map((p) => [p.periodo, p.total_consultas]),
    )
    return Array.from({ length: 14 }, (_, i) => {
      const d   = subDays(hoje, 13 - i)
      const key = format(d, "yyyy-MM-dd")
      return {
        key,
        label:  format(d, "EEE", { locale: dateFnsLocale }),
        value:  periodoMap.get(key) ?? 0,
        isHoje: isToday(d),
      }
    })
  }, [financeiroData])

  // ── Funil map ─────────────────────────────────────────────────────────────

  const funilMap = useMemo(
    () => new Map(funilData.map((f) => [f.etapa, f.total])),
    [funilData],
  )
  const funilMax = Math.max(...funilData.map((f) => f.total), 1)

  // ── Last updated ──────────────────────────────────────────────────────────

  const lastUpdated = kpisAt
    ? formatDistanceToNow(kpisAt, { addSuffix: true, locale: dateFnsLocale })
    : null

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs text-surface-400 capitalize">
            {format(hoje, "EEEE, d 'de' MMMM 'de' yyyy", { locale: dateFnsLocale })}
          </p>
          <h1 className="text-lg font-bold text-surface-800 mt-0.5">Visão geral</h1>
        </div>

        <button
          onClick={() => refetchKpis()}
          disabled={fetchingKpis}
          className="flex items-center gap-1.5 text-xs text-surface-400 hover:text-surface-600
                     px-3 py-1.5 rounded-lg hover:bg-surface-100 transition-colors"
        >
          <RefreshCw size={12} className={fetchingKpis ? "animate-spin" : ""} />
          {lastUpdated ? `actualizado ${lastUpdated}` : "actualizar"}
        </button>
      </div>

      {/* ── KPI cards ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          Icon={CalendarCheck2}
          label="Consultas hoje"
          value={consultasHoje}
          sub={pendentes > 0 ? `${pendentes} a aguardar` : "Todas processadas"}
          accent="blue"
        />
        <KpiCard
          Icon={HeartPulse}
          label="Comparecimento"
          value={comparecimento !== null ? `${comparecimento}%` : "—"}
          sub={comparecimento === null ? "Sem dados hoje" : comparecimento >= 80 ? "Boa taxa" : "Abaixo do ideal"}
          accent={comparecimento === null ? "slate" : comparecimento >= 80 ? "green" : "red"}
        />
        <KpiCard
          Icon={Users}
          label="Novos pacientes"
          value={kpis?.pacientes_novos ?? "—"}
          sub="este mês"
          accent="purple"
        />
        <KpiCard
          Icon={TrendingUp}
          label="Receita realizada"
          value={kpis != null ? formatCurrency(kpis.receita_realizada_eur, pais) : "—"}
          sub={`taxa faltas ${kpis?.taxa_falta_pct ?? "—"}%`}
          accent="green"
        />
      </div>

      {/* ── Charts row ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

        {/* Bar chart — consultas por dia */}
        <div className="xl:col-span-2 bg-white rounded-2xl border border-surface-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-surface-800">Consultas por dia</h2>
              <p className="text-xs text-surface-400 mt-0.5">últimos 14 dias</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-surface-400">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-brand-500 inline-block" />
                hoje
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-surface-200 inline-block" />
                passado
              </span>
            </div>
          </div>
          <BarChart data={barData} dateFnsLocale={dateFnsLocale} />
        </div>

        {/* Pipeline funil */}
        <div className="bg-white rounded-2xl border border-surface-100 shadow-sm p-5">
          <div className="mb-4">
            <h2 className="text-sm font-semibold text-surface-800">Pipeline</h2>
            <p className="text-xs text-surface-400 mt-0.5">conversão por etapa</p>
          </div>

          <div className="space-y-3">
            {FUNIL_ETAPAS.map((etapa, i) => {
              const count = funilMap.get(etapa.key as never) ?? 0
              const w     = pct(count, funilMax)
              const prev  = i > 0 ? (funilMap.get(FUNIL_ETAPAS[i - 1].key as never) ?? 0) : null
              const conv  = prev !== null && prev > 0 ? pct(count, prev) : null

              return (
                <div key={etapa.key}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-surface-500 font-medium">{etapa.label}</span>
                    <div className="flex items-center gap-2">
                      {conv !== null && (
                        <span className={`flex items-center gap-0.5 ${conv >= 50 ? "text-emerald-500" : "text-orange-400"}`}>
                          <ArrowRight size={9} />
                          {conv}%
                        </span>
                      )}
                      <span className="font-semibold text-surface-700 w-6 text-right">{count}</span>
                    </div>
                  </div>
                  <div className="h-2 bg-surface-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${etapa.cls}`}
                      style={{ width: `${w}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>

          <div className="mt-4 pt-3 border-t border-surface-50">
            <p className="text-xs text-surface-400">
              Total pipeline:{" "}
              <span className="font-semibold text-surface-700">
                {funilData.reduce((s, f) => s + f.total, 0)} pacientes
              </span>
            </p>
          </div>
        </div>
      </div>

      {/* ── Agenda hoje ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-surface-100 shadow-sm">
        <div className="px-5 py-4 border-b border-surface-50 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-surface-800">Agenda de hoje</h2>
          <span className="text-xs text-surface-400 bg-surface-100 px-2.5 py-1 rounded-full">
            {agendaHoje.length} consulta{agendaHoje.length !== 1 ? "s" : ""}
          </span>
        </div>

        {agendaHoje.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-surface-400 gap-2">
            <CalendarCheck2 size={28} className="opacity-30" />
            <p className="text-sm">Nenhuma consulta hoje</p>
          </div>
        ) : (
          <div className="divide-y divide-surface-50">
            {[...agendaHoje]
              .sort((a, b) => a.data_hora.localeCompare(b.data_hora))
              .map((c) => {
                const cfg  = STATUS_CFG[c.status] ?? STATUS_CFG.agendada
                const hora = format(parseISO(c.data_hora), "HH:mm")
                return (
                  <AgendaRow key={c.id} hora={hora} consulta={c} cfg={cfg} pais={pais} />
                )
              })}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── KPI card ─────────────────────────────────────────────────────────────────

const ACCENT: Record<string, { icon: string; border: string }> = {
  blue:   { icon: "bg-blue-50 text-blue-600",     border: "border-blue-100" },
  green:  { icon: "bg-emerald-50 text-emerald-600", border: "border-emerald-100" },
  red:    { icon: "bg-red-50 text-red-600",         border: "border-red-100" },
  purple: { icon: "bg-purple-50 text-purple-600",   border: "border-purple-100" },
  slate:  { icon: "bg-slate-100 text-slate-500",    border: "border-slate-100" },
}

function KpiCard({
  Icon,
  label,
  value,
  sub,
  accent,
}: {
  Icon: typeof CalendarCheck2
  label: string
  value: string | number
  sub: string
  accent: keyof typeof ACCENT
}) {
  const a = ACCENT[accent] ?? ACCENT.slate
  return (
    <div className={`bg-white rounded-2xl border ${a.border} shadow-sm px-5 py-4`}>
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-3 ${a.icon}`}>
        <Icon size={17} />
      </div>
      <p className="text-2xl font-bold text-surface-800 tracking-tight">{value}</p>
      <p className="text-xs font-medium text-surface-600 mt-0.5">{label}</p>
      <p className="text-xs text-surface-400 mt-0.5 truncate">{sub}</p>
    </div>
  )
}

// ─── SVG bar chart ────────────────────────────────────────────────────────────

interface BarDatum {
  key: string
  label: string
  value: number
  isHoje: boolean
}

function BarChart({ data, dateFnsLocale }: { data: BarDatum[]; dateFnsLocale: Locale }) {
  const W  = 560
  const H  = 140
  const PL = 28   // left padding (Y axis)
  const PB = 24   // bottom padding (X labels)
  const PR = 4
  const PT = 8

  const chartW = W - PL - PR
  const chartH = H - PB - PT

  const maxVal = Math.max(...data.map((d) => d.value), 1)

  // Y axis grid lines (4 lines: 0, 25%, 50%, 75%, 100%)
  const yLines = [0, 0.25, 0.5, 0.75, 1].map((f) => ({
    y:     PT + chartH * (1 - f),
    label: String(Math.round(maxVal * f)),
  }))

  const barW   = (chartW / data.length) * 0.55
  const barGap = chartW / data.length

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ height: 160 }}
      aria-label="Consultas por dia"
    >
      {/* Y grid lines */}
      {yLines.map(({ y, label }) => (
        <g key={y}>
          <line
            x1={PL} y1={y} x2={W - PR} y2={y}
            stroke="#f1f5f9" strokeWidth={1}
          />
          <text
            x={PL - 4} y={y + 4}
            textAnchor="end"
            fontSize={9}
            fill="#94a3b8"
          >
            {label}
          </text>
        </g>
      ))}

      {/* Bars */}
      {data.map((d, i) => {
        const x    = PL + i * barGap + (barGap - barW) / 2
        const barH = d.value > 0 ? (d.value / maxVal) * chartH : 0
        const y    = PT + chartH - barH

        return (
          <g key={d.key}>
            {/* Bar */}
            <rect
              x={x}
              y={y}
              width={barW}
              height={barH}
              rx={3}
              fill={d.isHoje ? "#6d28d9" : "#e2e8f0"}
              className="transition-all duration-300"
            />

            {/* Value label on top (only if > 0) */}
            {d.value > 0 && (
              <text
                x={x + barW / 2}
                y={y - 4}
                textAnchor="middle"
                fontSize={9}
                fontWeight={d.isHoje ? "700" : "400"}
                fill={d.isHoje ? "#6d28d9" : "#94a3b8"}
              >
                {d.value}
              </text>
            )}

            {/* Day label */}
            <text
              x={x + barW / 2}
              y={H - 4}
              textAnchor="middle"
              fontSize={9}
              fill={d.isHoje ? "#6d28d9" : "#94a3b8"}
              fontWeight={d.isHoje ? "700" : "400"}
              className="capitalize"
            >
              {d.label}
            </text>

            {/* Today marker dot */}
            {d.isHoje && (
              <circle
                cx={x + barW / 2}
                cy={H - PB + 2}
                r={2.5}
                fill="#6d28d9"
              />
            )}

            {/* Tooltip (native title) */}
            <title>
              {format(parseISO(d.key), "d MMM yyyy", { locale: dateFnsLocale })}: {d.value} consulta{d.value !== 1 ? "s" : ""}
            </title>
            {/* Transparent hit area for tooltip */}
            <rect
              x={x - barGap * 0.2}
              y={PT}
              width={barGap * 0.9}
              height={chartH}
              fill="transparent"
            >
              <title>
                {format(parseISO(d.key), "d MMM", { locale: dateFnsLocale })}: {d.value} consulta{d.value !== 1 ? "s" : ""}
              </title>
            </rect>
          </g>
        )
      })}

      {/* X axis baseline */}
      <line
        x1={PL} y1={PT + chartH}
        x2={W - PR} y2={PT + chartH}
        stroke="#e2e8f0" strokeWidth={1}
      />
    </svg>
  )
}

// ─── Agenda row ───────────────────────────────────────────────────────────────

function AgendaRow({
  hora,
  consulta,
  cfg,
  pais = "PT",
}: {
  hora: string
  consulta: Consulta
  cfg: { label: string; cls: string; Icon: typeof Clock }
  pais?: string
}) {
  const { Icon, label, cls } = cfg
  return (
    <div className="px-5 py-3 flex items-center gap-4 hover:bg-surface-50 transition-colors">
      <span className="text-sm font-mono font-semibold text-surface-500 w-10 shrink-0">{hora}</span>

      {/* Patient + doctor */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-surface-800 truncate">
          {consulta.pacientes?.nome ?? "—"}
        </p>
        <p className="text-xs text-surface-400 truncate">
          {consulta.medicos?.nome ?? "—"}
          {consulta.tipo && (
            <span className="ml-1 capitalize opacity-70">· {consulta.tipo.replace("_", " ")}</span>
          )}
        </p>
      </div>

      {/* Valor */}
      {consulta.valor != null && (
        <span className="text-xs font-mono text-surface-500 shrink-0 hidden sm:block">
          {formatCurrency(consulta.valor, pais)}
        </span>
      )}

      {/* Status badge */}
      <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium shrink-0 ${cls}`}>
        <Icon size={11} />
        {label}
      </span>
    </div>
  )
}
