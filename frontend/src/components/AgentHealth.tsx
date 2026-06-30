import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Activity, AlertTriangle, CheckCircle2, Shield,
  Users, DollarSign, Clock, BookOpen, Loader2, RefreshCw,
} from "lucide-react"
import http from "../services/http"
import { handleError } from "../services/errors"

// ─── Types ────────────────────────────────────────────────────────────────────

interface HealthMetrics {
  period: string
  total_runs: number
  sandbox_runs: number
  production_runs: number
  total_cost_usd: number
  avg_cost_usd: number
  avg_latency_ms: number
  p95_latency_ms: number
  total_tokens_in: number
  total_tokens_out: number
  kb_miss_rate: number
  hallucination_rate: number
  handover_rate: number
  pii_rate: number
}

type Period = "7d" | "30d"

async function fetchHealth(period: Period): Promise<HealthMetrics> {
  try {
    const res = await http.get(`/api/v1/agents/health?period=${period}`)
    return res.data as HealthMetrics
  } catch (e) {
    throw handleError(e)
  }
}

// ─── Metric card ──────────────────────────────────────────────────────────────

type AlertLevel = "ok" | "warn" | "error" | "info"

function MetricCard({
  Icon,
  label,
  value,
  sub,
  level = "ok",
}: {
  Icon: typeof Activity
  label: string
  value: string | number
  sub?: string
  level?: AlertLevel
}) {
  const colors: Record<AlertLevel, { bg: string; icon: string; badge: string }> = {
    ok:    { bg: "bg-white border-surface-100",         icon: "bg-emerald-50 text-emerald-600",  badge: "" },
    info:  { bg: "bg-white border-surface-100",         icon: "bg-blue-50 text-blue-600",        badge: "" },
    warn:  { bg: "bg-amber-50 border-amber-100",        icon: "bg-amber-100 text-amber-600",     badge: "⚠️" },
    error: { bg: "bg-red-50 border-red-100",            icon: "bg-red-100 text-red-600",         badge: "🔴" },
  }
  const clr = colors[level]

  return (
    <div className={`rounded-2xl border px-4 py-4 ${clr.bg} shadow-sm`}>
      <div className={`w-8 h-8 rounded-xl flex items-center justify-center mb-3 ${clr.icon}`}>
        <Icon size={15} />
      </div>
      <p className="text-xl font-bold text-surface-800 tracking-tight">
        {clr.badge} {value}
      </p>
      <p className="text-xs font-medium text-surface-600 mt-0.5">{label}</p>
      {sub && <p className="text-xs text-surface-400 mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function AgentHealth() {
  const [period, setPeriod] = useState<Period>("7d")

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["agent-health", period],
    queryFn:  () => fetchHealth(period),
    staleTime: 60_000,
    retry: 1,
  })

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={15} className="text-brand-600" />
          <p className="text-sm font-semibold text-surface-800">Saúde do Agente</p>
        </div>

        <div className="flex items-center gap-2">
          {/* Period toggle */}
          <div className="flex rounded-lg border border-surface-200 overflow-hidden">
            {(["7d", "30d"] as Period[]).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  period === p
                    ? "bg-surface-800 text-white"
                    : "bg-white text-surface-500 hover:bg-surface-50"
                }`}
              >
                {p === "7d" ? "7 dias" : "30 dias"}
              </button>
            ))}
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-1.5 rounded-lg text-surface-400 hover:text-surface-600 hover:bg-surface-100 transition-colors"
          >
            <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Loading / error states */}
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={20} className="animate-spin text-brand-500" />
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2.5 text-sm text-red-600">
          <AlertTriangle size={14} />
          {(error as Error).message}
        </div>
      )}

      {/* No data */}
      {data && data.total_runs === 0 && (
        <div className="rounded-xl border border-dashed border-surface-200 px-5 py-8 text-center">
          <Activity size={24} className="mx-auto text-surface-300 mb-2" />
          <p className="text-sm text-surface-500">Nenhum run registado nos últimos {period}.</p>
          <p className="text-xs text-surface-400 mt-1">
            Usa o "Testar agente" abaixo para gerar dados de sandbox.
          </p>
        </div>
      )}

      {/* Metrics grid */}
      {data && data.total_runs > 0 && (
        <>
          {/* Run summary */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            <MetricCard
              Icon={Activity}
              label="Total de runs"
              value={data.total_runs}
              sub={`${data.production_runs} produção · ${data.sandbox_runs} sandbox`}
              level="ok"
            />
            <MetricCard
              Icon={DollarSign}
              label="Custo total"
              value={`$${data.total_cost_usd.toFixed(4)}`}
              sub={`$${data.avg_cost_usd.toFixed(6)} / run`}
              level="ok"
            />
            <MetricCard
              Icon={Clock}
              label="Latência média"
              value={`${Math.round(data.avg_latency_ms)} ms`}
              sub={`p95: ${Math.round(data.p95_latency_ms)} ms`}
              level={data.avg_latency_ms > 8000 ? "warn" : "ok"}
            />
            <MetricCard
              Icon={Users}
              label="Handover humano"
              value={`${data.handover_rate}%`}
              sub="escalado para equipa"
              level="info"
            />
          </div>

          {/* Quality flags */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            <MetricCard
              Icon={BookOpen}
              label="KB Miss Rate"
              value={`${data.kb_miss_rate}%`}
              sub={data.kb_miss_rate > 10 ? "Alta — verifica o seed KB" : "Dentro do normal"}
              level={data.kb_miss_rate > 10 ? "warn" : "ok"}
            />
            <MetricCard
              Icon={AlertTriangle}
              label="Hallucination Risk"
              value={`${data.hallucination_rate}%`}
              sub={data.hallucination_rate > 5 ? "Forçar search_kb no prompt" : "Dentro do normal"}
              level={data.hallucination_rate > 5 ? "error" : "ok"}
            />
            <MetricCard
              Icon={Shield}
              label="PII / LGPD"
              value={data.pii_rate === 0 ? "Limpo" : `${data.pii_rate}%`}
              sub={data.pii_rate > 0 ? "CPF/email detectado nas respostas" : "Sem PII detectado"}
              level={data.pii_rate > 0 ? "error" : "ok"}
            />
            <MetricCard
              Icon={CheckCircle2}
              label="Tokens total"
              value={`${(data.total_tokens_in + data.total_tokens_out).toLocaleString()}`}
              sub={`↑${data.total_tokens_in.toLocaleString()} ↓${data.total_tokens_out.toLocaleString()}`}
              level="info"
            />
          </div>

          {/* Threshold legend */}
          <p className="text-[10px] text-surface-400">
            Alertas: KB Miss &gt; 10% ⚠️ · Hallucination Risk &gt; 5% 🔴 · Latência média &gt; 8 000 ms ⚠️
          </p>
        </>
      )}
    </div>
  )
}
