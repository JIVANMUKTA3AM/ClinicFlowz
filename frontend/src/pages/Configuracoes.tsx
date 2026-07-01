import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  MessageSquare, Zap, CheckCircle2, XCircle, Loader2,
  AlertCircle, Save, Radio, Settings, ChevronDown, ChevronUp,
  QrCode, Smartphone, RefreshCw, Bot, ChevronRight, Lock,
  BookOpen, Plus, Pencil, EyeOff, GitBranch,
} from "lucide-react"
import { integracoesService } from "../services/integracoes.service"
import { agentesService } from "../services/agentes.service"
import { kbService } from "../services/kb.service"
import { SandboxTester } from "../components/SandboxTester"
import { AgentHealth } from "../components/AgentHealth"
import { AgentVersions } from "../components/AgentVersions"
import type {
  Integracao, StatusIntegracao, TipoIntegracao,
  QRResult, SessaoStatus,
} from "../services/integracoes.service"
import type { WaAgent, AgentPlaybook, PlaybookStage } from "../services/agentes.service"
import type { KbEntity, KbCategory, KbCreateDTO } from "../services/kb.service"
import { KB_CATEGORY_LABELS } from "../services/kb.service"

// ─── Helpers ──────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: StatusIntegracao }) {
  const cfg = {
    conectado:    { cls: "bg-emerald-500",  label: "Conectado" },
    desconectado: { cls: "bg-surface-300",  label: "Desconectado" },
    erro:         { cls: "bg-red-500",      label: "Erro" },
  }[status] ?? { cls: "bg-surface-300", label: status }

  return (
    <span className="flex items-center gap-1.5 text-xs text-surface-500">
      <span className={`w-2 h-2 rounded-full ${cfg.cls}`} />
      {cfg.label}
    </span>
  )
}

function fieldCls(err = false) {
  return `w-full rounded-lg border ${
    err ? "border-red-300 bg-red-50" : "border-surface-200 bg-surface-50"
  } px-3.5 py-2.5 text-sm text-surface-900 placeholder-surface-400
  focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition`
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-medium text-surface-700 mb-1">{children}</label>
}

// ─── WhatsApp Tab ─────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 3000

function AbaWhatsApp({ integracao }: { integracao: Integracao | undefined }) {
  const qc = useQueryClient()

  // ── Config form ─────────────────────────────────────────────────────────────
  const [wahaUrl,      setWahaUrl]      = useState("")
  const [instanceName, setInstanceName] = useState("")
  const [apiKey,       setApiKey]       = useState("")
  const [showAdvanced, setShowAdvanced] = useState(!integracao)

  // ── QR / sessão ─────────────────────────────────────────────────────────────
  const [qrData,       setQrData]       = useState<QRResult | null>(null)
  const [sessao,       setSessao]       = useState<SessaoStatus | null>(null)
  const [qrError,      setQrError]      = useState<string | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (integracao) {
      setWahaUrl(integracao.config.waha_url ?? "")
      setInstanceName(integracao.config.instance_name ?? "")
      setApiKey("")
    }
  }, [integracao])

  // Limpa polling quando componente desmonta ou sessão conecta
  useEffect(() => {
    return () => { if (pollingRef.current) clearInterval(pollingRef.current) }
  }, [])

  function iniciarPolling() {
    if (pollingRef.current) clearInterval(pollingRef.current)
    pollingRef.current = setInterval(async () => {
      try {
        const s = await integracoesService.statusSessao()
        setSessao(s)
        if (s.conectado) {
          clearInterval(pollingRef.current!)
          pollingRef.current = null
          qc.invalidateQueries({ queryKey: ["integracoes"] })
        }
      } catch {
        // erros de polling não interrompem o fluxo
      }
    }, POLL_INTERVAL_MS)
  }

  // ── Mutations ────────────────────────────────────────────────────────────────

  const salvar = useMutation({
    mutationFn: () =>
      integracoesService.salvar({
        tipo:   "whatsapp",
        config: { waha_url: wahaUrl.trim(), instance_name: instanceName.trim() },
        ativo:  true,
        ...(apiKey ? { credenciais: apiKey } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integracoes"] })
      setApiKey("")
      setShowAdvanced(false)
    },
  })

  const conectar = useMutation({
    mutationFn: () => integracoesService.conectarQR(),
    onSuccess: (r) => {
      setQrData(r)
      setQrError(null)
      setSessao(null)
      iniciarPolling()
    },
    onError: (e: Error) => {
      setQrError(e.message)
      setQrData(null)
    },
  })

  function resetarQR() {
    if (pollingRef.current) clearInterval(pollingRef.current)
    setQrData(null)
    setSessao(null)
    setQrError(null)
  }

  const estaConectado = integracao?.status === "conectado" || sessao?.conectado

  // ─────────────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-surface-800">WhatsApp via WAHA</h2>
          <p className="text-xs text-surface-400 mt-0.5">
            Instância WAHA auto-hospedada — autenticação por QR Code
          </p>
        </div>
        {integracao && <StatusDot status={estaConectado ? "conectado" : integracao.status} />}
      </div>

      {/* ── Estado: conectado ─────────────────────────────────────────────── */}
      {estaConectado && (
        <div className="flex items-center gap-3 rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-3">
          <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
          <div>
            <p className="text-sm font-medium text-emerald-800">WhatsApp conectado</p>
            {(sessao?.telefone || sessao?.nome) && (
              <p className="text-xs text-emerald-600 mt-0.5">
                {sessao.nome && <span>{sessao.nome}</span>}
                {sessao.telefone && (
                  <span className="ml-1 font-mono">
                    ({sessao.telefone.replace("@c.us", "").replace("@s.whatsapp.net", "")})
                  </span>
                )}
              </p>
            )}
          </div>
          <button
            onClick={resetarQR}
            className="ml-auto text-xs text-emerald-600 hover:text-emerald-800 flex items-center gap-1"
          >
            <RefreshCw size={12} /> Reconectar
          </button>
        </div>
      )}

      {/* ── Fluxo QR ─────────────────────────────────────────────────────── */}
      {!estaConectado && (
        <>
          {/* Botão principal: Conectar */}
          {!qrData && (
            <button
              onClick={() => conectar.mutate()}
              disabled={conectar.isPending || !integracao}
              title={!integracao ? "Configure e guarde os dados de servidor antes de conectar" : undefined}
              className="w-full flex items-center justify-center gap-2.5 py-3 rounded-xl
                         bg-brand-600 text-white text-sm font-semibold
                         hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {conectar.isPending
                ? <><Loader2 size={16} className="animate-spin" /> A gerar QR Code…</>
                : <><QrCode size={16} /> Conectar via QR Code</>
              }
            </button>
          )}

          {/* Erro ao gerar QR */}
          {qrError && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
              <AlertCircle size={15} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-medium">Não foi possível gerar o QR Code</p>
                <p className="mt-0.5 text-xs text-red-600">{qrError}</p>
              </div>
            </div>
          )}

          {/* QR Code + polling ────────────────────────────────────────────── */}
          {qrData && (
            <div className="space-y-4">
              <div className="flex flex-col items-center gap-4 rounded-xl border-2 border-dashed border-surface-200 p-6">
                <img
                  src={qrData.qr_code}
                  alt="QR Code WhatsApp"
                  className="w-52 h-52 rounded-lg"
                />
                <div className="flex items-center gap-2 text-surface-500 text-xs">
                  <Smartphone size={14} />
                  <span>{qrData.instrucao}</span>
                </div>
              </div>

              {/* Indicador de polling */}
              {!sessao?.conectado && (
                <div className="flex items-center gap-2 text-xs text-surface-400">
                  <Loader2 size={12} className="animate-spin" />
                  A aguardar que escaneie o código…
                  {sessao?.waha_status && (
                    <span className="ml-1 font-mono bg-surface-100 px-1.5 py-0.5 rounded">
                      {sessao.waha_status}
                    </span>
                  )}
                </div>
              )}

              <button
                onClick={resetarQR}
                className="text-xs text-surface-400 hover:text-surface-600 flex items-center gap-1"
              >
                <XCircle size={12} /> Cancelar
              </button>
            </div>
          )}
        </>
      )}

      {/* ── Configuração avançada (colapsável) ───────────────────────────── */}
      <div className="border border-surface-100 rounded-xl overflow-hidden">
        <button
          onClick={() => setShowAdvanced((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 text-xs font-medium
                     text-surface-500 hover:bg-surface-50 transition-colors"
        >
          <span>Configuração do servidor WAHA</span>
          {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {showAdvanced && (
          <div className="px-4 pb-4 space-y-4 border-t border-surface-100 pt-4">
            <div>
              <Label>URL do servidor WAHA</Label>
              <input
                type="url"
                value={wahaUrl}
                onChange={(e) => setWahaUrl(e.target.value)}
                placeholder="https://waha.exemplo.com"
                className={fieldCls()}
              />
            </div>

            <div>
              <Label>Nome da sessão</Label>
              <input
                type="text"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
                placeholder="clinica-abc"
                className={fieldCls()}
              />
              <p className="text-xs text-surface-400 mt-1">
                Identificador único da sessão no servidor WAHA
              </p>
            </div>

            <div>
              <Label>
                API Key
                {integracao?.tem_credencial && (
                  <span className="text-surface-400 font-normal ml-1">
                    (configurada — deixe em branco para manter)
                  </span>
                )}
              </Label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={integracao?.tem_credencial ? "••••••••" : "Chave API do WAHA"}
                className={fieldCls()}
                autoComplete="new-password"
              />
            </div>

            {salvar.isError && (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2.5 text-sm text-red-700">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                {(salvar.error as Error).message}
              </div>
            )}

            <button
              onClick={() => salvar.mutate()}
              disabled={salvar.isPending}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-surface-800 text-white
                         text-sm font-medium hover:bg-surface-900 disabled:opacity-50 transition-colors"
            >
              {salvar.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Guardar configuração
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Kommo Tab ────────────────────────────────────────────────────────────────

function AbaKommo({ integracao }: { integracao: Integracao | undefined }) {
  const qc = useQueryClient()

  const [subdomain,   setSubdomain]   = useState("")
  const [token,       setToken]       = useState("")
  const [testeResult, setTesteResult] = useState<{ ok: boolean; detalhe?: string } | null>(null)

  useEffect(() => {
    if (integracao) {
      setSubdomain(integracao.config.subdomain ?? "")
      setToken("")
    }
  }, [integracao])

  const salvar = useMutation({
    mutationFn: () =>
      integracoesService.salvar({
        tipo:   "kommo",
        config: { subdomain: subdomain.trim() },
        ativo:  true,
        ...(token ? { credenciais: token } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integracoes"] })
      setToken("")
    },
  })

  const testar = useMutation({
    mutationFn: () => integracoesService.testar("kommo"),
    onSuccess: (r) => {
      setTesteResult({ ok: r.ok, detalhe: r.detalhe })
      qc.invalidateQueries({ queryKey: ["integracoes"] })
    },
  })

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-surface-800">Kommo CRM</h2>
          <p className="text-xs text-surface-400 mt-0.5">
            Sincronize leads e pacientes com o Kommo
          </p>
        </div>
        {integracao && <StatusDot status={integracao.status} />}
      </div>

      <div className="space-y-4">
        <div>
          <Label>Subdomínio Kommo</Label>
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={subdomain}
              onChange={(e) => setSubdomain(e.target.value)}
              placeholder="minha-clinica"
              className={`${fieldCls()} flex-1`}
            />
            <span className="text-sm text-surface-400 shrink-0">.kommo.com</span>
          </div>
          <p className="text-xs text-surface-400 mt-1">
            Ex: se o URL é minha-clinica.kommo.com, o subdomínio é <code className="bg-surface-100 px-1 rounded">minha-clinica</code>
          </p>
        </div>

        <div>
          <Label>
            Token de longa duração
            {integracao?.tem_credencial && (
              <span className="text-surface-400 font-normal ml-1">(configurado — deixe em branco para manter)</span>
            )}
          </Label>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder={integracao?.tem_credencial ? "••••••••" : "Access token do Kommo"}
            className={fieldCls()}
            autoComplete="new-password"
          />
          <p className="text-xs text-surface-400 mt-1">
            Kommo → Perfil → Integrações → Tokens de API → Token de longa duração
          </p>
        </div>
      </div>

      {/* Resultado do teste */}
      {testeResult && (
        <div className={`flex items-start gap-2 rounded-lg px-4 py-3 text-sm ${
          testeResult.ok
            ? "bg-emerald-50 border border-emerald-100 text-emerald-700"
            : "bg-red-50 border border-red-100 text-red-700"
        }`}>
          {testeResult.ok
            ? <CheckCircle2 size={15} className="mt-0.5 shrink-0" />
            : <XCircle     size={15} className="mt-0.5 shrink-0" />
          }
          <span>{testeResult.detalhe ?? (testeResult.ok ? "Autenticação válida." : "Erro na autenticação.")}</span>
        </div>
      )}

      {salvar.isError && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          {(salvar.error as Error).message}
        </div>
      )}

      <div className="flex gap-3 pt-1">
        <button
          onClick={() => salvar.mutate()}
          disabled={salvar.isPending}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-brand-600 text-white text-sm
                     font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {salvar.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Guardar
        </button>

        <button
          onClick={() => { setTesteResult(null); testar.mutate() }}
          disabled={testar.isPending || !integracao}
          title={!integracao ? "Guarde primeiro antes de testar" : undefined}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-surface-200
                     text-sm text-surface-600 hover:bg-surface-50 disabled:opacity-40 transition-colors"
        >
          {testar.isPending ? <Loader2 size={14} className="animate-spin" /> : <Radio size={14} />}
          Testar conexão
        </button>
      </div>
    </div>
  )
}

// ─── Agente IA Tab ────────────────────────────────────────────────────────────

const STAGE_COLORS: Record<string, { bg: string; border: string; dot: string }> = {
  opening:       { bg: "bg-blue-50",    border: "border-blue-100",   dot: "bg-blue-400" },
  discovery:     { bg: "bg-violet-50",  border: "border-violet-100", dot: "bg-violet-400" },
  qualification: { bg: "bg-amber-50",   border: "border-amber-100",  dot: "bg-amber-400" },
  scheduling:    { bg: "bg-emerald-50", border: "border-emerald-100",dot: "bg-emerald-500" },
  closing:       { bg: "bg-surface-50", border: "border-surface-100",dot: "bg-surface-400" },
}

function StageCard({ stage, index }: { stage: PlaybookStage; index: number }) {
  const clr = STAGE_COLORS[stage.id] ?? STAGE_COLORS.closing
  return (
    <div className={`rounded-xl border ${clr.border} ${clr.bg} p-4 space-y-3`}>
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className={`w-5 h-5 rounded-full ${clr.dot} flex items-center justify-center text-white text-[10px] font-bold shrink-0`}>
          {index + 1}
        </span>
        <span className="text-sm font-semibold text-surface-800">{stage.label}</span>
        {stage.blocked_tools.length > 0 && (
          <span className="ml-auto flex items-center gap-1 text-xs text-amber-600 bg-amber-100 px-2 py-0.5 rounded-full">
            <Lock size={10} />
            {stage.blocked_tools.length} tool{stage.blocked_tools.length !== 1 ? "s" : ""} bloqueada{stage.blocked_tools.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Goals */}
      {stage.goals.length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-surface-500 uppercase tracking-wide mb-1">Objetivos</p>
          <ul className="space-y-0.5">
            {stage.goals.map((g, i) => (
              <li key={i} className="text-xs text-surface-700 flex items-start gap-1.5">
                <ChevronRight size={10} className="mt-0.5 shrink-0 text-surface-400" />
                {g}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Blocked tools */}
      {stage.blocked_tools.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {stage.blocked_tools.map((t) => (
            <span key={t} className="text-[10px] font-mono bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function AbaAgente({ agent }: { agent: WaAgent | undefined }) {
  const qc = useQueryClient()
  const [jsonText, setJsonText]       = useState("")
  const [jsonError, setJsonError]     = useState<string | null>(null)
  const [showEditor, setShowEditor]   = useState(false)

  const playbook: AgentPlaybook | null = agent?.agent_playbook ?? null

  useEffect(() => {
    if (agent?.agent_playbook) {
      setJsonText(JSON.stringify(agent.agent_playbook, null, 2))
    }
  }, [agent])

  const salvar = useMutation({
    mutationFn: () => {
      if (!agent) throw new Error("Agente não carregado")
      let parsed: AgentPlaybook
      try {
        parsed = JSON.parse(jsonText)
      } catch {
        throw new Error("JSON inválido. Verifica a sintaxe antes de guardar.")
      }
      return agentesService.updatePlaybook(agent.id, parsed)
    },
    onSuccess: () => {
      setJsonError(null)
      qc.invalidateQueries({ queryKey: ["wa-agent"] })
    },
    onError: (e: Error) => setJsonError(e.message),
  })

  if (!agent) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={24} className="animate-spin text-brand-500" />
      </div>
    )
  }

  const stages: PlaybookStage[] = playbook?.stages ?? []

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-surface-800">{agent.nome}</h2>
          <p className="text-xs text-surface-400 mt-0.5">Playbook de conversa — state machine do agente</p>
        </div>
        <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium ${
          agent.ativo
            ? "bg-emerald-50 text-emerald-700"
            : "bg-surface-100 text-surface-500"
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${agent.ativo ? "bg-emerald-500" : "bg-surface-400"}`} />
          {agent.ativo ? "Activo" : "Inactivo"}
        </span>
      </div>

      {/* Health dashboard */}
      <div className="border border-surface-100 rounded-xl px-4 py-4">
        <AgentHealth />
      </div>

      {/* Stage flow */}
      {stages.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium text-surface-500 uppercase tracking-wide">Funil de conversa</p>
          <div className="grid gap-2">
            {stages.map((s, i) => (
              <StageCard key={s.id} stage={s} index={i} />
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-surface-200 p-6 text-center text-sm text-surface-400">
          Nenhum stage configurado. Usa o editor JSON abaixo para configurar o playbook.
        </div>
      )}

      {/* Sandbox tester */}
      <div className="border border-surface-100 rounded-xl px-4 py-4 bg-surface-50/30">
        <SandboxTester />
      </div>

      {/* JSON editor */}
      <div className="border border-surface-100 rounded-xl overflow-hidden">
        <button
          onClick={() => setShowEditor((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 text-xs font-medium
                     text-surface-500 hover:bg-surface-50 transition-colors"
        >
          <span>Editor JSON do playbook</span>
          {showEditor ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {showEditor && (
          <div className="px-4 pb-4 border-t border-surface-100 pt-4 space-y-3">
            <textarea
              value={jsonText}
              onChange={(e) => { setJsonText(e.target.value); setJsonError(null) }}
              rows={20}
              spellCheck={false}
              className="w-full font-mono text-xs rounded-lg border border-surface-200 bg-surface-50
                         px-3 py-2.5 text-surface-900 focus:outline-none focus:ring-2
                         focus:ring-brand-500/20 focus:border-brand-400 transition resize-y"
            />

            {(salvar.isError || jsonError) && (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2.5 text-sm text-red-700">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                {jsonError ?? (salvar.error as Error)?.message}
              </div>
            )}

            {salvar.isSuccess && (
              <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-100 px-3 py-2.5 text-sm text-emerald-700">
                <CheckCircle2 size={14} />
                Playbook guardado com sucesso.
              </div>
            )}

            <button
              onClick={() => salvar.mutate()}
              disabled={salvar.isPending}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-surface-800 text-white
                         text-sm font-medium hover:bg-surface-900 disabled:opacity-50 transition-colors"
            >
              {salvar.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Guardar playbook
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── KB Tab ───────────────────────────────────────────────────────────────────

const CATEGORY_COLORS: Record<KbCategory, string> = {
  empresa:      "bg-blue-50 text-blue-700 border-blue-100",
  contato:      "bg-slate-50 text-slate-600 border-slate-100",
  servico:      "bg-violet-50 text-violet-700 border-violet-100",
  precificacao: "bg-amber-50 text-amber-700 border-amber-100",
  faq:          "bg-emerald-50 text-emerald-700 border-emerald-100",
  politica:     "bg-rose-50 text-rose-700 border-rose-100",
}

const KB_CATEGORIES = Object.keys(KB_CATEGORY_LABELS) as KbCategory[]

interface KbFormState {
  category: KbCategory
  title: string
  content: string
}

const EMPTY_FORM: KbFormState = { category: "empresa", title: "", content: "" }

function AbaKB() {
  const qc = useQueryClient()
  const [editingId, setEditingId]   = useState<string | null>(null)
  const [form, setForm]             = useState<KbFormState>(EMPTY_FORM)
  const [showForm, setShowForm]     = useState(false)
  const [filterCat, setFilterCat]   = useState<KbCategory | "">("")

  const { data: entities = [], isLoading } = useQuery({
    queryKey: ["kb-entities", filterCat],
    queryFn: () => kbService.list(filterCat || undefined),
    staleTime: 30_000,
  })

  const save = useMutation({
    mutationFn: () => {
      if (!form.title.trim() || !form.content.trim()) throw new Error("Título e conteúdo são obrigatórios.")
      if (editingId) {
        return kbService.update(editingId, { title: form.title, content: form.content, category: form.category })
      }
      return kbService.create(form as KbCreateDTO)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-entities"] })
      setShowForm(false)
      setEditingId(null)
      setForm(EMPTY_FORM)
    },
  })

  const deactivate = useMutation({
    mutationFn: (id: string) => kbService.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kb-entities"] }),
  })

  function startEdit(e: KbEntity) {
    setEditingId(e.id)
    setForm({ category: e.category, title: e.title, content: e.content })
    setShowForm(true)
  }

  function cancelForm() {
    setShowForm(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
    save.reset()
  }

  // Group by category
  const grouped = KB_CATEGORIES.reduce<Record<KbCategory, KbEntity[]>>((acc, cat) => {
    acc[cat] = entities.filter((e) => e.category === cat && e.active)
    return acc
  }, {} as Record<KbCategory, KbEntity[]>)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-surface-800">Base de Conhecimento</h2>
          <p className="text-xs text-surface-400 mt-0.5">
            Informações que o agente consulta para responder pacientes
          </p>
        </div>
        <button
          onClick={() => { setShowForm(true); setEditingId(null); setForm(EMPTY_FORM) }}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-brand-600 text-white text-xs
                     font-medium hover:bg-brand-700 transition-colors"
        >
          <Plus size={13} /> Adicionar
        </button>
      </div>

      {/* Category filter */}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setFilterCat("")}
          className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
            filterCat === "" ? "bg-surface-800 text-white border-surface-800" : "bg-white text-surface-500 border-surface-200 hover:bg-surface-50"
          }`}
        >
          Todos
        </button>
        {KB_CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilterCat(cat === filterCat ? "" : cat)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              filterCat === cat ? CATEGORY_COLORS[cat] + " font-semibold" : "bg-white text-surface-500 border-surface-200 hover:bg-surface-50"
            }`}
          >
            {KB_CATEGORY_LABELS[cat]}
          </button>
        ))}
      </div>

      {/* Add/Edit form */}
      {showForm && (
        <div className="border border-brand-200 rounded-xl bg-brand-50/30 p-4 space-y-3">
          <p className="text-xs font-semibold text-surface-700">
            {editingId ? "Editar entrada" : "Nova entrada"}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1">Categoria</label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value as KbCategory })}
                className="w-full rounded-lg border border-surface-200 bg-white px-3 py-2 text-sm text-surface-900 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              >
                {KB_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{KB_CATEGORY_LABELS[c]}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1">Título</label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Ex: Quanto custa botox?"
                className="w-full rounded-lg border border-surface-200 bg-white px-3 py-2 text-sm text-surface-900 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-surface-600 mb-1">Conteúdo</label>
            <textarea
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              rows={5}
              placeholder="Texto completo que o agente irá consultar..."
              className="w-full rounded-lg border border-surface-200 bg-white px-3 py-2 text-sm text-surface-900 focus:outline-none focus:ring-2 focus:ring-brand-500/20 resize-y"
            />
          </div>
          {save.isError && (
            <p className="text-xs text-red-600 flex items-center gap-1">
              <AlertCircle size={12} /> {(save.error as Error).message}
            </p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-surface-800 text-white text-xs font-medium hover:bg-surface-900 disabled:opacity-50"
            >
              {save.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              Guardar
            </button>
            <button onClick={cancelForm} className="px-4 py-2 rounded-lg text-xs text-surface-500 hover:bg-surface-100">
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Entity list grouped by category */}
      {isLoading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 size={20} className="animate-spin text-brand-500" />
        </div>
      ) : entities.filter((e) => e.active).length === 0 ? (
        <div className="rounded-xl border border-dashed border-surface-200 p-8 text-center text-sm text-surface-400">
          Nenhuma entrada na base de conhecimento. Clica em "Adicionar" para começar.
        </div>
      ) : (
        <div className="space-y-4">
          {KB_CATEGORIES.map((cat) => {
            const rows = filterCat ? (filterCat === cat ? grouped[cat] : []) : grouped[cat]
            if (rows.length === 0) return null
            return (
              <div key={cat}>
                <p className="text-xs font-semibold text-surface-500 uppercase tracking-wide mb-2">
                  {KB_CATEGORY_LABELS[cat]} ({rows.length})
                </p>
                <div className="space-y-2">
                  {rows.map((e) => (
                    <div
                      key={e.id}
                      className={`rounded-lg border px-4 py-3 flex items-start gap-3 ${CATEGORY_COLORS[e.category]}`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold truncate">{e.title}</p>
                        <p className="text-xs opacity-70 mt-0.5 line-clamp-2">{e.content}</p>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button
                          onClick={() => startEdit(e)}
                          title="Editar"
                          className="p-1.5 rounded hover:bg-black/10 transition-colors"
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          onClick={() => deactivate.mutate(e.id)}
                          title="Desativar"
                          className="p-1.5 rounded hover:bg-black/10 transition-colors opacity-60"
                        >
                          <EyeOff size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

type Aba = "whatsapp" | "kommo" | "agente" | "kb" | "versoes"

const ABAS: { id: Aba; label: string; Icon: typeof MessageSquare }[] = [
  { id: "whatsapp", label: "WhatsApp / WAHA", Icon: MessageSquare },
  { id: "kommo",    label: "Kommo CRM",       Icon: Zap },
  { id: "agente",   label: "Agente IA",       Icon: Bot },
  { id: "kb",       label: "Conhecimento",    Icon: BookOpen },
  { id: "versoes",  label: "Versões",         Icon: GitBranch },
]

export function Configuracoes() {
  const [aba, setAba] = useState<Aba>("whatsapp")

  const { data: integracoes = [], isLoading: loadingIntegracoes } = useQuery({
    queryKey: ["integracoes"],
    queryFn: integracoesService.listar,
    staleTime: 30_000,
  })

  const { data: agent, isLoading: loadingAgent } = useQuery({
    queryKey: ["wa-agent"],
    queryFn: agentesService.get,
    staleTime: 60_000,
    enabled: aba === "agente" || aba === "versoes",
  })

  // KB loading handled inside AbaKB component itself

  const isLoading = loadingIntegracoes || (aba === "agente" && loadingAgent)
  const byTipo = Object.fromEntries(integracoes.map((i) => [i.tipo, i])) as Partial<Record<Aba, Integracao>>

  return (
    <div className="max-w-2xl space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-brand-50 flex items-center justify-center">
          <Settings size={17} className="text-brand-600" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-surface-800">Configurações</h1>
          <p className="text-xs text-surface-400">Integrações com sistemas de terceiros</p>
        </div>
      </div>

      {/* Card com abas */}
      <div className="bg-white rounded-2xl border border-surface-100 shadow-sm overflow-hidden">

        {/* Aba selector */}
        <div className="flex border-b border-surface-100">
          {ABAS.map(({ id, label, Icon }) => {
            const integracao = byTipo[id]
            return (
              <button
                key={id}
                onClick={() => setAba(id)}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-3.5 text-sm
                            font-medium transition-colors relative ${
                  aba === id
                    ? "text-brand-700 bg-brand-50/50"
                    : "text-surface-500 hover:text-surface-700 hover:bg-surface-50"
                }`}
              >
                <Icon size={15} />
                {label}
                {integracao && (
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    integracao.status === "conectado" ? "bg-emerald-500" :
                    integracao.status === "erro"      ? "bg-red-500" :
                                                        "bg-surface-300"
                  }`} />
                )}
                {aba === id && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-600" />
                )}
              </button>
            )
          })}
        </div>

        {/* Conteúdo da aba */}
        <div className="p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={24} className="animate-spin text-brand-500" />
            </div>
          ) : aba === "whatsapp" ? (
            <AbaWhatsApp integracao={byTipo.whatsapp} />
          ) : aba === "kommo" ? (
            <AbaKommo integracao={byTipo.kommo} />
          ) : aba === "agente" ? (
            <AbaAgente agent={agent} />
          ) : aba === "kb" ? (
            <AbaKB />
          ) : (
            agent
              ? <AgentVersions agentId={agent.id} />
              : <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-brand-500" /></div>
          )}
        </div>
      </div>

      {/* Aviso de segurança */}
      <div className="flex items-start gap-2 text-xs text-surface-400">
        <AlertCircle size={13} className="mt-0.5 shrink-0 text-amber-400" />
        <span>
          Os tokens e chaves API são cifrados antes de serem guardados — nunca ficam em texto puro na base de dados.
        </span>
      </div>
    </div>
  )
}
