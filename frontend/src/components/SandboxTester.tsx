import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import {
  FlaskConical, Loader2, AlertTriangle, CheckCircle2,
  ChevronDown, ChevronUp, Zap, Database, Shield,
} from "lucide-react"
import http from "../services/http"
import { handleError } from "../services/errors"

// ─── Types ────────────────────────────────────────────────────────────────────

type Scenario = "new_lead" | "returning_patient" | "hot_lead"

interface ToolCall {
  tool: string
  simulated: boolean
  result_preview: string
}

interface SandboxResult {
  reply_chunks: string[]
  tools_called: ToolCall[]
  stage_after: string
  context_snapshot_after: Record<string, unknown>
  cost_usd: number
  tokens: { in: number; out: number }
  latency_ms: number
  guardrail_flags: string[]
}

const SCENARIO_LABELS: Record<Scenario, string> = {
  new_lead:          "Novo lead",
  returning_patient: "Paciente recorrente",
  hot_lead:          "Lead quente (qualification)",
}

const SCENARIO_DESCRIPTIONS: Record<Scenario, string> = {
  new_lead:          "Sem histórico, contexto vazio",
  returning_patient: "ai_profile com 2 consultas e preferências",
  hot_lead:          "Stage=qualification, botox confirmado",
}

const STAGE_COLORS: Record<string, string> = {
  opening:       "text-blue-600 bg-blue-50",
  discovery:     "text-violet-600 bg-violet-50",
  qualification: "text-amber-600 bg-amber-50",
  scheduling:    "text-emerald-600 bg-emerald-50",
  closing:       "text-slate-600 bg-slate-50",
}

// ─── Component ────────────────────────────────────────────────────────────────

export function SandboxTester() {
  const [message,  setMessage]  = useState("Oi! Quero saber mais sobre botox, quanto custa?")
  const [scenario, setScenario] = useState<Scenario>("new_lead")
  const [simulate, setSimulate] = useState(true)
  const [showSnap, setShowSnap] = useState(false)

  const run = useMutation({
    mutationFn: async (): Promise<SandboxResult> => {
      try {
        const res = await http.post("/api/v1/sandbox/run", {
          contact_scenario: scenario,
          messages: [{ role: "user", content: message }],
          simulate_tools: simulate,
        })
        return res.data as SandboxResult
      } catch (e) {
        throw handleError(e)
      }
    },
  })

  const result = run.data

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <FlaskConical size={16} className="text-brand-600" />
        <div>
          <p className="text-sm font-semibold text-surface-800">Testar agente</p>
          <p className="text-xs text-surface-400">
            Roda o agente completo sem enviar mensagem real no WhatsApp
          </p>
        </div>
      </div>

      {/* Scenario selector */}
      <div className="grid grid-cols-3 gap-2">
        {(Object.keys(SCENARIO_LABELS) as Scenario[]).map((s) => (
          <button
            key={s}
            onClick={() => setScenario(s)}
            className={`rounded-lg border px-3 py-2.5 text-left transition-colors ${
              scenario === s
                ? "border-brand-300 bg-brand-50"
                : "border-surface-200 hover:bg-surface-50"
            }`}
          >
            <p className={`text-xs font-semibold ${scenario === s ? "text-brand-700" : "text-surface-700"}`}>
              {SCENARIO_LABELS[s]}
            </p>
            <p className="text-[10px] text-surface-400 mt-0.5">{SCENARIO_DESCRIPTIONS[s]}</p>
          </button>
        ))}
      </div>

      {/* Message input */}
      <div>
        <label className="block text-xs font-medium text-surface-600 mb-1">
          Mensagem do paciente
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={3}
          placeholder="Digite a mensagem que o paciente enviaria..."
          className="w-full rounded-lg border border-surface-200 bg-surface-50 px-3 py-2.5 text-sm
                     text-surface-900 focus:outline-none focus:ring-2 focus:ring-brand-500/20
                     focus:border-brand-400 transition resize-none"
        />
      </div>

      {/* Options row */}
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={simulate}
            onChange={(e) => setSimulate(e.target.checked)}
            className="rounded border-surface-300 text-brand-600 focus:ring-brand-500"
          />
          <span className="text-xs text-surface-600">Simular tools de escrita</span>
        </label>

        <button
          onClick={() => run.mutate()}
          disabled={run.isPending || !message.trim()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 text-white text-sm
                     font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {run.isPending
            ? <><Loader2 size={14} className="animate-spin" /> A correr…</>
            : <><FlaskConical size={14} /> Testar</>
          }
        </button>
      </div>

      {/* Error */}
      {run.isError && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2.5 text-sm text-red-700">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          {(run.error as Error).message}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-4 border-t border-surface-100 pt-4">

          {/* Guardrail flags */}
          {result.guardrail_flags.length > 0 && (
            <div className="rounded-lg bg-amber-50 border border-amber-100 px-3 py-2.5 space-y-1">
              <p className="text-xs font-semibold text-amber-700 flex items-center gap-1.5">
                <Shield size={12} /> Avisos do guardrail
              </p>
              {result.guardrail_flags.map((f, i) => (
                <p key={i} className="text-xs text-amber-600 font-mono">{f}</p>
              ))}
            </div>
          )}

          {/* Reply chunks */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-surface-600">Resposta do agente</p>
            {result.reply_chunks.map((chunk, i) => (
              <div
                key={i}
                className="rounded-lg bg-surface-50 border border-surface-100 px-4 py-3 text-sm text-surface-800 whitespace-pre-wrap"
              >
                {i > 0 && (
                  <span className="block text-[10px] text-surface-400 mb-1 font-mono">
                    chunk {i + 1}/{result.reply_chunks.length}
                  </span>
                )}
                {chunk}
              </div>
            ))}
          </div>

          {/* Tools called */}
          {result.tools_called.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-surface-600 mb-2">Tools chamadas</p>
              <div className="space-y-1">
                {result.tools_called.map((t, i) => (
                  <div key={i} className={`flex items-start gap-2.5 rounded-lg px-3 py-2 text-xs ${
                    t.simulated ? "bg-amber-50 border border-amber-100" : "bg-surface-50 border border-surface-100"
                  }`}>
                    {t.simulated
                      ? <Zap size={11} className="mt-0.5 text-amber-500 shrink-0" />
                      : <Database size={11} className="mt-0.5 text-emerald-500 shrink-0" />
                    }
                    <div className="min-w-0">
                      <span className="font-mono font-semibold text-surface-700">{t.tool}</span>
                      {t.simulated && (
                        <span className="ml-2 text-amber-600 bg-amber-100 px-1 rounded text-[10px]">simulado</span>
                      )}
                      <p className="text-surface-400 truncate mt-0.5">{t.result_preview}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Metrics */}
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "Stage final",  value: result.stage_after,
                cls: STAGE_COLORS[result.stage_after] ?? "text-surface-600 bg-surface-50" },
              { label: "Latência",     value: `${result.latency_ms} ms`,      cls: "text-surface-600 bg-surface-50" },
              { label: "Tokens",       value: `${result.tokens.in}↑ ${result.tokens.out}↓`, cls: "text-surface-600 bg-surface-50" },
              { label: "Custo",        value: `$${result.cost_usd.toFixed(4)}`, cls: "text-surface-600 bg-surface-50" },
            ].map(({ label, value, cls }) => (
              <div key={label} className={`rounded-lg px-3 py-2 text-center ${cls}`}>
                <p className="text-[10px] opacity-70">{label}</p>
                <p className="text-xs font-semibold font-mono mt-0.5">{value}</p>
              </div>
            ))}
          </div>

          {/* Snapshot toggle */}
          <button
            onClick={() => setShowSnap((v) => !v)}
            className="text-xs text-surface-400 hover:text-surface-600 flex items-center gap-1"
          >
            {showSnap ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            context_snapshot_after
          </button>
          {showSnap && (
            <pre className="text-[10px] font-mono bg-surface-50 border border-surface-100 rounded-lg p-3 overflow-auto max-h-48 text-surface-600">
              {JSON.stringify(result.context_snapshot_after, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
