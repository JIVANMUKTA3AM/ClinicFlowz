import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  MessageSquare, Zap, CheckCircle2, XCircle, Loader2,
  AlertCircle, Save, Radio, Settings, ChevronDown, ChevronUp,
  QrCode, Smartphone, RefreshCw,
} from "lucide-react"
import { integracoesService } from "../services/integracoes.service"
import type {
  Integracao, StatusIntegracao, TipoIntegracao,
  QRResult, SessaoStatus,
} from "../services/integracoes.service"

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

// ─── Main page ────────────────────────────────────────────────────────────────

type Aba = "whatsapp" | "kommo"

const ABAS: { id: Aba; label: string; Icon: typeof MessageSquare }[] = [
  { id: "whatsapp", label: "WhatsApp / WAHA", Icon: MessageSquare },
  { id: "kommo",    label: "Kommo CRM",       Icon: Zap },
]

export function Configuracoes() {
  const [aba, setAba] = useState<Aba>("whatsapp")

  const { data: integracoes = [], isLoading } = useQuery({
    queryKey: ["integracoes"],
    queryFn: integracoesService.listar,
    staleTime: 30_000,
  })

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
          ) : (
            <AbaKommo integracao={byTipo.kommo} />
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
