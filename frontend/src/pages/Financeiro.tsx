import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { format, subDays, startOfMonth } from "date-fns"
import {
  TrendingUp, TrendingDown, DollarSign, Users,
  AlertCircle, CheckCircle2, Calendar,
} from "lucide-react"
import { financeiroService } from "../services/financeiro.service"
import { useAuthStore } from "../store/authStore"
import { formatCurrency } from "../lib/locale"

// ─── Period presets ───────────────────────────────────────────────────────────

const hoje = () => format(new Date(), "yyyy-MM-dd")

const PERIODOS = [
  { label: "Este mês",    inicio: () => format(startOfMonth(new Date()), "yyyy-MM-dd"), fim: hoje },
  { label: "Últimos 30d", inicio: () => format(subDays(new Date(), 29), "yyyy-MM-dd"), fim: hoje },
  { label: "Últimos 90d", inicio: () => format(subDays(new Date(), 89), "yyyy-MM-dd"), fim: hoje },
] as const

// ─── KPI card ─────────────────────────────────────────────────────────────────

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  accent = "slate",
}: {
  icon: typeof TrendingUp
  label: string
  value: string
  sub?: string
  accent?: "green" | "blue" | "red" | "amber" | "slate"
}) {
  const cls = {
    green: "bg-emerald-50 text-emerald-600",
    blue:  "bg-blue-50 text-blue-600",
    red:   "bg-red-50 text-red-600",
    amber: "bg-amber-50 text-amber-600",
    slate: "bg-surface-100 text-surface-500",
  }[accent]

  return (
    <div className="bg-white rounded-2xl border border-surface-100 shadow-sm px-5 py-4">
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-3 ${cls}`}>
        <Icon size={17} />
      </div>
      <p className="text-2xl font-bold text-surface-800 tracking-tight">{value}</p>
      <p className="text-xs font-medium text-surface-600 mt-0.5">{label}</p>
      {sub && <p className="text-xs text-surface-400 mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function Financeiro() {
  const pais = useAuthStore((s) => s.user?.pais ?? "PT")

  const [periodoIdx, setPeriodoIdx] = useState(0)
  const periodo = PERIODOS[periodoIdx]
  const dataInicio = periodo.inicio()
  const dataFim    = periodo.fim()

  const { data: resumo, isLoading: loadingResumo } = useQuery({
    queryKey: ["financeiro-resumo", dataInicio, dataFim],
    queryFn: () => financeiroService.resumo({ data_inicio: dataInicio, data_fim: dataFim, agrupar_por: "mes" }),
    staleTime: 60_000,
  })

  const { data: comissoesData, isLoading: loadingComissoes } = useQuery({
    queryKey: ["financeiro-comissoes", dataInicio, dataFim],
    queryFn: () => financeiroService.comissoes({ data_inicio: dataInicio, data_fim: dataFim }),
    staleTime: 60_000,
  })

  const isLoading = loadingResumo || loadingComissoes

  return (
    <div className="space-y-5">

      {/* ── Header + period selector ──────────────────────────────────────── */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-bold text-surface-800">Financeiro</h1>
          <p className="text-xs text-surface-400 mt-0.5">
            {dataInicio} → {dataFim}
          </p>
        </div>

        <div className="flex gap-1.5">
          {PERIODOS.map((p, i) => (
            <button
              key={p.label}
              onClick={() => setPeriodoIdx(i)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                periodoIdx === i
                  ? "bg-brand-600 text-white border-brand-600"
                  : "border-surface-200 text-surface-500 hover:border-brand-300 hover:text-brand-600"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── KPI cards ─────────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white rounded-2xl border border-surface-100 shadow-sm px-5 py-4 animate-pulse">
              <div className="w-9 h-9 rounded-xl bg-surface-100 mb-3" />
              <div className="h-7 w-24 bg-surface-100 rounded mb-2" />
              <div className="h-3 w-20 bg-surface-100 rounded" />
            </div>
          ))}
        </div>
      ) : resumo ? (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <KpiCard
            icon={TrendingUp}
            label="Receita total"
            value={formatCurrency(resumo.receita_total, pais)}
            sub={`${resumo.total_consultas} consulta${resumo.total_consultas !== 1 ? "s" : ""}`}
            accent="green"
          />
          <KpiCard
            icon={CheckCircle2}
            label="Receita recebida"
            value={formatCurrency(resumo.receita_paga, pais)}
            sub={`${resumo.consultas_pagas} paga${resumo.consultas_pagas !== 1 ? "s" : ""}`}
            accent="blue"
          />
          <KpiCard
            icon={AlertCircle}
            label="Receita pendente"
            value={formatCurrency(resumo.receita_pendente, pais)}
            sub={`${resumo.consultas_pendentes} pendente${resumo.consultas_pendentes !== 1 ? "s" : ""}`}
            accent={resumo.receita_pendente > 0 ? "amber" : "slate"}
          />
          <KpiCard
            icon={DollarSign}
            label="Ticket médio"
            value={formatCurrency(resumo.ticket_medio, pais)}
            sub={`inadimplência ${resumo.taxa_inadimplencia_pct.toFixed(1)}%`}
            accent={resumo.taxa_inadimplencia_pct > 15 ? "red" : "slate"}
          />
        </div>
      ) : null}

      {/* ── Receita por médico + Comissões ────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

        {/* Receita por médico */}
        <div className="bg-white rounded-2xl border border-surface-100 shadow-sm">
          <div className="px-5 py-4 border-b border-surface-50 flex items-center gap-2">
            <Users size={15} className="text-surface-400" />
            <h2 className="text-sm font-semibold text-surface-800">Receita por médico</h2>
          </div>

          {isLoading ? (
            <div className="px-5 py-6 space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-10 bg-surface-100 rounded animate-pulse" />)}
            </div>
          ) : resumo?.por_medico?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-50">
                    <th className="text-left text-xs font-medium text-surface-400 px-5 py-2.5">Médico</th>
                    <th className="text-right text-xs font-medium text-surface-400 px-3 py-2.5">Consultas</th>
                    <th className="text-right text-xs font-medium text-surface-400 px-3 py-2.5">Total</th>
                    <th className="text-right text-xs font-medium text-surface-400 px-5 py-2.5">Pago</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-50">
                  {resumo.por_medico.map((m) => (
                    <tr key={m.medico_id} className="hover:bg-surface-50 transition-colors">
                      <td className="px-5 py-3">
                        <p className="text-sm font-medium text-surface-800 truncate">{m.medico_nome}</p>
                        <p className="text-xs text-surface-400">{m.especialidade}</p>
                      </td>
                      <td className="px-3 py-3 text-right text-sm text-surface-500">{m.total_consultas}</td>
                      <td className="px-3 py-3 text-right text-sm font-medium text-surface-700">
                        {formatCurrency(m.receita_total, pais)}
                      </td>
                      <td className="px-5 py-3 text-right">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          m.receita_pendente > 0
                            ? "bg-amber-50 text-amber-700"
                            : "bg-emerald-50 text-emerald-700"
                        }`}>
                          {formatCurrency(m.receita_paga, pais)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-surface-100 bg-surface-50">
                    <td className="px-5 py-2.5 text-xs font-semibold text-surface-600">Total</td>
                    <td className="px-3 py-2.5 text-right text-xs font-semibold text-surface-600">
                      {resumo.total_consultas}
                    </td>
                    <td className="px-3 py-2.5 text-right text-xs font-semibold text-surface-700">
                      {formatCurrency(resumo.receita_total, pais)}
                    </td>
                    <td className="px-5 py-2.5 text-right text-xs font-semibold text-emerald-700">
                      {formatCurrency(resumo.receita_paga, pais)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-10 text-surface-400 gap-2">
              <TrendingDown size={24} className="opacity-40" />
              <p className="text-sm">Sem dados no período</p>
            </div>
          )}
        </div>

        {/* Comissões */}
        <div className="bg-white rounded-2xl border border-surface-100 shadow-sm">
          <div className="px-5 py-4 border-b border-surface-50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Calendar size={15} className="text-surface-400" />
              <h2 className="text-sm font-semibold text-surface-800">Comissões</h2>
            </div>
            {comissoesData && (
              <span className="text-xs font-semibold text-surface-700 bg-surface-100 px-2.5 py-1 rounded-full">
                Total: {formatCurrency(comissoesData.total_comissoes, pais)}
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="px-5 py-6 space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-10 bg-surface-100 rounded animate-pulse" />)}
            </div>
          ) : comissoesData?.comissoes?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-50">
                    <th className="text-left text-xs font-medium text-surface-400 px-5 py-2.5">Médico</th>
                    <th className="text-right text-xs font-medium text-surface-400 px-3 py-2.5">%</th>
                    <th className="text-right text-xs font-medium text-surface-400 px-3 py-2.5">Base</th>
                    <th className="text-right text-xs font-medium text-surface-400 px-5 py-2.5">Comissão</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-50">
                  {comissoesData.comissoes.map((c) => (
                    <tr key={c.medico_id} className="hover:bg-surface-50 transition-colors">
                      <td className="px-5 py-3">
                        <p className="text-sm font-medium text-surface-800 truncate">{c.medico_nome}</p>
                        <p className="text-xs text-surface-400">
                          {c.consultas_realizadas} consulta{c.consultas_realizadas !== 1 ? "s" : ""}
                        </p>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <span className="text-xs bg-surface-100 text-surface-600 px-2 py-0.5 rounded font-mono">
                          {c.comissao_pct.toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-3 py-3 text-right text-sm text-surface-500">
                        {formatCurrency(c.receita_base, pais)}
                      </td>
                      <td className="px-5 py-3 text-right text-sm font-semibold text-brand-700">
                        {formatCurrency(c.comissao_valor, pais)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-surface-100 bg-surface-50">
                    <td colSpan={3} className="px-5 py-2.5 text-xs font-semibold text-surface-600">Total comissões</td>
                    <td className="px-5 py-2.5 text-right text-xs font-semibold text-brand-700">
                      {formatCurrency(comissoesData.total_comissoes, pais)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-10 text-surface-400 gap-2">
              <DollarSign size={24} className="opacity-40" />
              <p className="text-sm">Sem comissões no período</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Receita por período ───────────────────────────────────────────── */}
      {resumo?.por_periodo?.length ? (
        <div className="bg-white rounded-2xl border border-surface-100 shadow-sm">
          <div className="px-5 py-4 border-b border-surface-50">
            <h2 className="text-sm font-semibold text-surface-800">Evolução por período</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-50">
                  <th className="text-left text-xs font-medium text-surface-400 px-5 py-2.5">Período</th>
                  <th className="text-right text-xs font-medium text-surface-400 px-3 py-2.5">Consultas</th>
                  <th className="text-right text-xs font-medium text-surface-400 px-3 py-2.5">Total</th>
                  <th className="text-right text-xs font-medium text-surface-400 px-5 py-2.5">Pago</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-50">
                {resumo.por_periodo.map((p) => (
                  <tr key={p.periodo} className="hover:bg-surface-50 transition-colors">
                    <td className="px-5 py-2.5 text-sm font-medium text-surface-700 font-mono">{p.periodo}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-surface-500">{p.total_consultas}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-surface-700">{formatCurrency(p.receita_total, pais)}</td>
                    <td className="px-5 py-2.5 text-right text-sm text-emerald-700 font-medium">{formatCurrency(p.receita_paga, pais)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

    </div>
  )
}
