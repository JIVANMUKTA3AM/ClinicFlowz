import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  GitBranch, CheckCircle2, XCircle, AlertTriangle, Loader2,
  Plus, Upload, RotateCcw, ChevronDown, ChevronUp, Lock,
} from "lucide-react"
import http from "../services/http"
import { handleError } from "../services/errors"

// ─── Types ────────────────────────────────────────────────────────────────────

interface ReadinessCriterion {
  criterion: string
  points: number
  earned: number
  ok: boolean
  note: string
}

interface Readiness {
  score: number
  breakdown: ReadinessCriterion[]
  blockers: string[]
  can_publish: boolean
}

interface AgentVersion {
  id: string
  version_number: number
  label: string | null
  readiness_score: number
  readiness_issues: string[]
  status: "staging" | "production"
  published_at: string | null
  created_at: string
  diff: string[]
}

// ─── Readiness bar ────────────────────────────────────────────────────────────

function ReadinessBar({ score, can_publish }: { score: number; can_publish: boolean }) {
  const color = score >= 70
    ? "bg-emerald-500"
    : score >= 40
    ? "bg-amber-400"
    : "bg-red-400"

  const labelColor = score >= 70 ? "text-emerald-700" : score >= 40 ? "text-amber-700" : "text-red-700"
  const bgLabel    = score >= 70 ? "bg-emerald-50" : score >= 40 ? "bg-amber-50" : "bg-red-50"

  return (
    <div className={`rounded-xl border px-4 py-4 ${bgLabel} ${score >= 70 ? "border-emerald-100" : score >= 40 ? "border-amber-100" : "border-red-100"}`}>
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className={`text-2xl font-bold ${labelColor}`}>{score}/100</p>
          <p className="text-xs text-surface-500 mt-0.5">Score de prontidão</p>
        </div>
        <div className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full ${
          can_publish ? "bg-emerald-100 text-emerald-700" : "bg-surface-100 text-surface-500"
        }`}>
          {can_publish ? <CheckCircle2 size={12} /> : <Lock size={12} />}
          {can_publish ? "Pronto para publicar" : score < 70 ? "Score insuficiente" : "Bloqueadores críticos"}
        </div>
      </div>
      <div className="h-3 bg-white/60 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${score}%` }}
        />
      </div>
      <p className="text-[10px] text-surface-400 mt-1">Mínimo para publicar: 70 pontos</p>
    </div>
  )
}

// ─── Criterion row ────────────────────────────────────────────────────────────

function CriterionRow({ c }: { c: ReadinessCriterion }) {
  return (
    <div className="flex items-start gap-2.5">
      {c.ok
        ? <CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" />
        : <XCircle      size={14} className="text-surface-300 mt-0.5 shrink-0" />
      }
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className={`text-xs font-medium ${c.ok ? "text-surface-700" : "text-surface-400"}`}>
            {c.criterion}
          </span>
          <span className={`text-xs font-mono ml-2 shrink-0 ${c.ok ? "text-emerald-600" : "text-surface-300"}`}>
            +{c.earned}/{c.points}
          </span>
        </div>
        <p className={`text-[10px] mt-0.5 ${c.ok ? "text-surface-400" : "text-amber-600"}`}>{c.note}</p>
      </div>
    </div>
  )
}

// ─── Version card ─────────────────────────────────────────────────────────────

function VersionCard({
  version,
  agentId,
  canPublishLatest,
  onPublish,
  onRestore,
}: {
  version: AgentVersion
  agentId: string
  canPublishLatest: boolean
  onPublish: (id: string) => void
  onRestore: (id: string) => void
}) {
  const [showDiff, setShowDiff] = useState(false)
  const isProd = version.status === "production"

  return (
    <div className={`rounded-xl border px-4 py-3 ${isProd ? "border-emerald-200 bg-emerald-50/30" : "border-surface-100 bg-white"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-mono font-bold text-surface-600">
              v{version.version_number}
            </span>
            {version.label && (
              <span className="text-xs text-surface-600 truncate">{version.label}</span>
            )}
            {isProd && (
              <span className="flex items-center gap-1 text-[10px] font-semibold bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
                <CheckCircle2 size={9} /> Em produção
              </span>
            )}
            {version.readiness_score !== null && (
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                version.readiness_score >= 70 ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
              }`}>
                {version.readiness_score}pts
              </span>
            )}
          </div>
          <p className="text-[10px] text-surface-400 mt-0.5">
            {new Date(version.created_at).toLocaleString("pt-PT", {
              day: "2-digit", month: "short", year: "numeric",
              hour: "2-digit", minute: "2-digit",
            })}
            {version.published_at && (
              <span className="ml-2 text-emerald-500">
                · publicado {new Date(version.published_at).toLocaleString("pt-PT", {
                  day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
                })}
              </span>
            )}
          </p>
        </div>

        <div className="flex gap-1.5 shrink-0">
          {!isProd && (
            <button
              onClick={() => onPublish(version.id)}
              disabled={!canPublishLatest}
              title={!canPublishLatest ? "Score insuficiente ou bloqueadores críticos" : "Publicar esta versão"}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium
                         bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Upload size={10} /> Publicar
            </button>
          )}
          {!isProd && (
            <button
              onClick={() => onRestore(version.id)}
              title="Restaurar configuração desta versão"
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium
                         border border-surface-200 text-surface-600 hover:bg-surface-50 transition-colors"
            >
              <RotateCcw size={10} /> Restaurar
            </button>
          )}
        </div>
      </div>

      {/* Diff */}
      {version.diff && version.diff.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowDiff((v) => !v)}
            className="flex items-center gap-1 text-[10px] text-surface-400 hover:text-surface-600"
          >
            {showDiff ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            {showDiff ? "ocultar" : `${version.diff.length} alteração(ões)`}
          </button>
          {showDiff && (
            <ul className="mt-1.5 space-y-0.5">
              {version.diff.map((d, i) => (
                <li key={i} className="text-[10px] text-surface-500 flex items-start gap-1.5">
                  <span className="text-surface-300 shrink-0">·</span>
                  {d}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Blockers */}
      {version.readiness_issues && version.readiness_issues.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {version.readiness_issues.map((issue, i) => (
            <span key={i} className="text-[10px] bg-red-50 text-red-600 border border-red-100 px-1.5 py-0.5 rounded">
              {issue}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function AgentVersions({ agentId }: { agentId: string }) {
  const qc = useQueryClient()
  const [label, setLabel]         = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [feedback, setFeedback]   = useState<{ ok: boolean; msg: string } | null>(null)

  // Readiness (real-time)
  const { data: readiness, isLoading: loadingR } = useQuery<Readiness>({
    queryKey: ["agent-readiness", agentId],
    queryFn:  async () => {
      const r = await http.get(`/api/v1/agent-versions/${agentId}/readiness`)
      return r.data
    },
    staleTime: 30_000,
  })

  // Versions list
  const { data: versions = [], isLoading: loadingV, refetch } = useQuery<AgentVersion[]>({
    queryKey: ["agent-versions", agentId],
    queryFn:  async () => {
      const r = await http.get(`/api/v1/agent-versions/${agentId}`)
      return r.data
    },
    staleTime: 30_000,
  })

  const createVersion = useMutation({
    mutationFn: async () => {
      await http.post(`/api/v1/agent-versions/${agentId}`, { label: label.trim() || null })
    },
    onSuccess: () => {
      setShowCreate(false)
      setLabel("")
      setFeedback({ ok: true, msg: "Versão criada com sucesso." })
      qc.invalidateQueries({ queryKey: ["agent-versions", agentId] })
    },
    onError: (e: Error) => setFeedback({ ok: false, msg: e.message }),
  })

  const publish = useMutation({
    mutationFn: async (versionId: string) => {
      await http.post(`/api/v1/agent-versions/${agentId}/${versionId}/publish`, {})
    },
    onSuccess: () => {
      setFeedback({ ok: true, msg: "Versão publicada em produção." })
      qc.invalidateQueries({ queryKey: ["agent-versions", agentId] })
      qc.invalidateQueries({ queryKey: ["agent-readiness", agentId] })
    },
    onError: (e: Error) => setFeedback({ ok: false, msg: e.message }),
  })

  const restore = useMutation({
    mutationFn: async (versionId: string) => {
      await http.post(`/api/v1/agent-versions/${agentId}/${versionId}/restore`, {})
    },
    onSuccess: () => {
      setFeedback({ ok: true, msg: "Versão restaurada. Nova versão criada automaticamente." })
      qc.invalidateQueries({ queryKey: ["agent-versions", agentId] })
      qc.invalidateQueries({ queryKey: ["agent-readiness", agentId] })
    },
    onError: (e: Error) => setFeedback({ ok: false, msg: e.message }),
  })

  const isLoading = loadingR || loadingV

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitBranch size={15} className="text-brand-600" />
          <p className="text-sm font-semibold text-surface-800">Versões do Agente</p>
        </div>
        <button
          onClick={() => { setShowCreate((v) => !v); setFeedback(null) }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-800 text-white text-xs font-medium hover:bg-surface-900 transition-colors"
        >
          <Plus size={12} /> Criar versão
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="border border-brand-200 bg-brand-50/30 rounded-xl p-4 space-y-3">
          <p className="text-xs font-semibold text-surface-700">Nova versão — snapshot do estado actual</p>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label opcional (ex: v2 — mais consultiva)"
            className="w-full rounded-lg border border-surface-200 bg-white px-3 py-2 text-sm text-surface-900 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
          />
          <div className="flex gap-2">
            <button
              onClick={() => createVersion.mutate()}
              disabled={createVersion.isPending}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-600 text-white text-xs font-medium hover:bg-brand-700 disabled:opacity-50"
            >
              {createVersion.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
              Capturar snapshot
            </button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-xs text-surface-500 hover:bg-surface-100 rounded-lg">
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Feedback */}
      {feedback && (
        <div className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm ${
          feedback.ok ? "bg-emerald-50 border border-emerald-100 text-emerald-700" : "bg-red-50 border border-red-100 text-red-700"
        }`}>
          {feedback.ok ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
          {feedback.msg}
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-brand-500" /></div>
      ) : (
        <>
          {/* Readiness score */}
          {readiness && (
            <div className="space-y-3">
              <ReadinessBar score={readiness.score} can_publish={readiness.can_publish} />

              {/* Blockers */}
              {readiness.blockers.length > 0 && (
                <div className="rounded-lg bg-red-50 border border-red-100 px-3 py-2.5 space-y-1">
                  <p className="text-xs font-semibold text-red-700 flex items-center gap-1.5">
                    <Lock size={12} /> Bloqueadores críticos
                  </p>
                  {readiness.blockers.map((b, i) => (
                    <p key={i} className="text-xs text-red-600">· {b}</p>
                  ))}
                </div>
              )}

              {/* Criteria checklist */}
              <div className="border border-surface-100 rounded-xl p-4 space-y-3">
                <p className="text-xs font-semibold text-surface-600">Critérios de prontidão</p>
                {readiness.breakdown.map((c, i) => (
                  <CriterionRow key={i} c={c} />
                ))}
              </div>
            </div>
          )}

          {/* Versions list */}
          {versions.length === 0 ? (
            <div className="rounded-xl border border-dashed border-surface-200 p-6 text-center text-sm text-surface-400">
              Nenhuma versão ainda. Clica em "Criar versão" para capturar o estado actual.
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-surface-500">
                {versions.length} versão(ões) — mais recentes primeiro
              </p>
              {versions.map((v) => (
                <VersionCard
                  key={v.id}
                  version={v}
                  agentId={agentId}
                  canPublishLatest={readiness?.can_publish ?? false}
                  onPublish={(id) => publish.mutate(id)}
                  onRestore={(id) => restore.mutate(id)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
