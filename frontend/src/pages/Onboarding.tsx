import { useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Stethoscope, Building2, UserRound, CheckCircle2,
  ChevronRight, Loader2, AlertCircle, ArrowRight, Globe,
} from "lucide-react"
import { supabase } from "../lib/supabase"
import { useAuthStore } from "../store/authStore"
import { onboardingService } from "../services/onboarding.service"
import { medicosService } from "../services/medicos.service"
import { getLocale } from "../lib/locale"
import type { Pais } from "../types"

// ─── Types ────────────────────────────────────────────────────────────────────

interface ClinicaForm {
  nome: string
  documento_fiscal: string
  telefone: string
  email: string
  morada: string
  cidade: string
}

interface MedicoForm {
  nome: string
  especialidade: string
  cedula: string
}

const CLINICA_EMPTY: ClinicaForm = { nome: "", documento_fiscal: "", telefone: "", email: "", morada: "", cidade: "" }
const MEDICO_EMPTY: MedicoForm   = { nome: "", especialidade: "", cedula: "" }

const ESPECIALIDADES = [
  "Medicina Geral e Familiar",
  "Medicina Dentária",
  "Ortodontia",
  "Implantologia",
  "Periodontia",
  "Endodontia",
  "Pediatria Dentária",
  "Dermatologia",
  "Cardiologia",
  "Ortopedia",
  "Ginecologia",
  "Oftalmologia",
  "Otorrinolaringologia",
  "Psicologia",
  "Nutrição",
  "Fisioterapia",
  "Outra",
]

// ─── Step indicator ───────────────────────────────────────────────────────────

function StepDot({ n, current, done }: { n: number; current: number; done: boolean }) {
  const active = n === current
  const complete = done || n < current

  return (
    <div className="flex items-center gap-2">
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all
          ${complete ? "bg-brand-600 text-white" : active ? "bg-brand-50 border-2 border-brand-600 text-brand-700" : "bg-surface-100 text-surface-400"}`}
      >
        {complete && n < current ? <CheckCircle2 size={16} /> : n}
      </div>
    </div>
  )
}

// step: 0=País, 1=Clínica, 2=Médico, 3=Pronto (displayed as 1-4)
function StepBar({ step }: { step: 0 | 1 | 2 | 3 }) {
  const STEPS = ["País", "Clínica", "Médico", "Pronto"]
  const uiStep = step + 1  // display 1-4
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEPS.map((label, i) => (
        <div key={label} className="flex items-center">
          <div className="flex flex-col items-center gap-1">
            <StepDot n={i + 1} current={uiStep} done={false} />
            <span className={`text-xs font-medium ${i + 1 === uiStep ? "text-brand-700" : i + 1 < uiStep ? "text-surface-500" : "text-surface-300"}`}>
              {label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={`h-0.5 w-12 mx-2 mb-4 rounded-full transition-all ${i + 1 < uiStep ? "bg-brand-400" : "bg-surface-200"}`} />
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Field helpers ────────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-medium text-surface-700 mb-1">{children}</label>
}

function inputCls(err = false) {
  return `w-full rounded-lg border ${err ? "border-red-300 bg-red-50" : "border-surface-200 bg-surface-50"} px-3.5 py-2.5 text-sm text-surface-900 placeholder-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition`
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function Onboarding() {
  const navigate = useNavigate()
  const user     = useAuthStore((s) => s.user)

  const [step,    setStep]    = useState<0 | 1 | 2 | 3>(0)
  const [pais,    setPais]    = useState<Pais | "">("")
  const [clinica, setClinica] = useState<ClinicaForm>(CLINICA_EMPTY)
  const [medico,  setMedico]  = useState<MedicoForm>(MEDICO_EMPTY)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)
  const [docFiscalWarn, setDocFiscalWarn] = useState<string | null>(null)
  const [clinicaNomeForDisplay, setClinicaNomeForDisplay] = useState("")

  const loc = pais ? getLocale(pais) : getLocale("PT")

  function fieldClinica<K extends keyof ClinicaForm>(k: K, v: ClinicaForm[K]) {
    setClinica((p) => ({ ...p, [k]: v }))
    if (k === "documento_fiscal") setDocFiscalWarn(null)
  }

  function validateDocFiscal(val: string) {
    if (!val || !pais) { setDocFiscalWarn(null); return }
    const digits = val.replace(/\D/g, "")
    if (pais === "PT" && digits.length > 0 && digits.length !== 9) {
      setDocFiscalWarn("NIF deve ter 9 dígitos")
    } else if (pais === "BR" && digits.length > 0 && digits.length !== 14) {
      setDocFiscalWarn("CNPJ deve ter 14 dígitos")
    } else {
      setDocFiscalWarn(null)
    }
  }

  function fieldMedico<K extends keyof MedicoForm>(k: K, v: MedicoForm[K]) {
    setMedico((p) => ({ ...p, [k]: v }))
  }

  // ── Step 0: selecionar país ────────────────────────────────────────────────

  function handleSelecionarPais(p: Pais) {
    setPais(p)
    setError(null)
    setStep(1)
  }

  // ── Step 1: criar clínica ──────────────────────────────────────────────────

  async function handleCriarClinica() {
    if (!clinica.nome.trim()) {
      setError("O nome da clínica é obrigatório")
      return
    }
    if (!pais) {
      setError("País não definido")
      return
    }
    setError(null)
    setLoading(true)
    try {
      await onboardingService.criarClinica({
        pais:                     pais,
        clinica_nome:             clinica.nome.trim(),
        clinica_documento_fiscal: clinica.documento_fiscal || undefined,
        clinica_telefone:         clinica.telefone          || undefined,
        clinica_email:            clinica.email             || undefined,
        clinica_morada:           clinica.morada            || undefined,
        clinica_cidade:           clinica.cidade            || undefined,
      })
      await supabase.auth.refreshSession()
      setClinicaNomeForDisplay(clinica.nome.trim())
      setStep(2)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || "Erro ao criar clínica. Tente novamente.")
    } finally {
      setLoading(false)
    }
  }

  // ── Step 2: criar médico (opcional) ───────────────────────────────────────

  async function handleCriarMedico() {
    if (!medico.nome.trim() || !medico.especialidade) {
      setError("Nome e especialidade são obrigatórios")
      return
    }
    setError(null)
    setLoading(true)
    try {
      await medicosService.criar({
        nome:          medico.nome.trim(),
        especialidade: medico.especialidade,
        cedula:        medico.cedula || undefined,
      })
      setStep(3)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || "Erro ao criar médico. Pode adicioná-lo mais tarde.")
    } finally {
      setLoading(false)
    }
  }

  function handleConcluir() {
    navigate("/dashboard", { replace: true })
  }

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gradient-to-br from-surface-50 to-brand-50/30 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-lg">

        {/* Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-brand-600 flex items-center justify-center mb-4 shadow-lg shadow-brand-600/30">
            <Stethoscope size={22} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-surface-900 tracking-tight">Configurar a sua clínica</h1>
          <p className="text-sm text-surface-500 mt-1">
            {user?.email && <span className="text-surface-400">{user.email} · </span>}
            Apenas alguns passos para começar
          </p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-surface-100 p-8">

          <StepBar step={step} />

          {/* ── STEP 0: Selecionar país ────────────────────────────────────── */}
          {step === 0 && (
            <div>
              <div className="flex items-center gap-2.5 mb-6">
                <div className="w-8 h-8 rounded-lg bg-brand-50 flex items-center justify-center">
                  <Globe size={16} className="text-brand-600" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-surface-800">Onde está a sua clínica?</h2>
                  <p className="text-xs text-surface-400">Adapta documentos fiscais, lei de privacidade e idioma dos assistentes</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => handleSelecionarPais("PT")}
                  className="flex flex-col items-center gap-3 p-6 rounded-xl border-2 border-surface-200
                             hover:border-brand-400 hover:bg-brand-50 transition-all group"
                >
                  <span className="text-4xl">🇵🇹</span>
                  <div className="text-center">
                    <p className="text-sm font-semibold text-surface-800 group-hover:text-brand-700">Portugal</p>
                    <p className="text-xs text-surface-400 mt-0.5">NIF · EUR · RGPD</p>
                  </div>
                </button>

                <button
                  onClick={() => handleSelecionarPais("BR")}
                  className="flex flex-col items-center gap-3 p-6 rounded-xl border-2 border-surface-200
                             hover:border-brand-400 hover:bg-brand-50 transition-all group"
                >
                  <span className="text-4xl">🇧🇷</span>
                  <div className="text-center">
                    <p className="text-sm font-semibold text-surface-800 group-hover:text-brand-700">Brasil</p>
                    <p className="text-xs text-surface-400 mt-0.5">CNPJ/CPF · BRL · LGPD</p>
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 1: Clínica ─────────────────────────────────────────────── */}
          {step === 1 && (
            <div className="space-y-1">
              <div className="flex items-center gap-2.5 mb-5">
                <div className="w-8 h-8 rounded-lg bg-brand-50 flex items-center justify-center">
                  <Building2 size={16} className="text-brand-600" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-surface-800">Dados da clínica</h2>
                  <p className="text-xs text-surface-400">Pode actualizar estes dados mais tarde</p>
                </div>
              </div>

              {error && (
                <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700 mb-4">
                  <AlertCircle size={15} className="mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <Label>Nome da clínica *</Label>
                  <input
                    type="text"
                    value={clinica.nome}
                    onChange={(e) => fieldClinica("nome", e.target.value)}
                    placeholder="Clínica Dentária Exemplo, Lda."
                    autoFocus
                    className={inputCls(!clinica.nome && !!error)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>
                      {loc.docFiscalClinicaLabel}
                      <span className="text-surface-400 font-normal ml-1">(opcional)</span>
                    </Label>
                    <input
                      type="text"
                      value={clinica.documento_fiscal}
                      onChange={(e) => fieldClinica("documento_fiscal", e.target.value)}
                      onBlur={(e) => validateDocFiscal(e.target.value)}
                      placeholder={loc.placeholderDocClinica}
                      className={inputCls(!!docFiscalWarn)}
                    />
                    {docFiscalWarn && (
                      <p className="text-xs text-amber-600 mt-1">{docFiscalWarn}</p>
                    )}
                  </div>
                  <div>
                    <Label>Telefone</Label>
                    <input
                      type="tel"
                      value={clinica.telefone}
                      onChange={(e) => fieldClinica("telefone", e.target.value)}
                      placeholder={loc.placeholderTel}
                      className={inputCls()}
                    />
                  </div>
                </div>

                <div>
                  <Label>Email da clínica</Label>
                  <input
                    type="email"
                    value={clinica.email}
                    onChange={(e) => fieldClinica("email", e.target.value)}
                    placeholder={pais === "PT" ? "geral@clinica.pt" : "contato@clinica.com.br"}
                    className={inputCls()}
                  />
                </div>

                <div>
                  <Label>Morada</Label>
                  <input
                    type="text"
                    value={clinica.morada}
                    onChange={(e) => fieldClinica("morada", e.target.value)}
                    placeholder={pais === "PT" ? "Rua Exemplo, nº 1, 2º Dto." : "Rua Exemplo, 123 — Sala 1"}
                    className={inputCls()}
                  />
                </div>

                <div>
                  <Label>Cidade</Label>
                  <input
                    type="text"
                    value={clinica.cidade}
                    onChange={(e) => fieldClinica("cidade", e.target.value)}
                    placeholder={pais === "PT" ? "Lisboa" : "São Paulo"}
                    className={inputCls()}
                  />
                </div>
              </div>

              <button
                onClick={handleCriarClinica}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 mt-6 rounded-lg bg-brand-600 px-4 py-2.5
                           text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-all"
              >
                {loading ? <><Loader2 size={15} className="animate-spin" />A criar…</> : <>Continuar <ChevronRight size={15} /></>}
              </button>
            </div>
          )}

          {/* ── STEP 2: Médico ──────────────────────────────────────────────── */}
          {step === 2 && (
            <div>
              <div className="flex items-center gap-2.5 mb-5">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center">
                  <UserRound size={16} className="text-indigo-600" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-surface-800">Primeiro médico</h2>
                  <p className="text-xs text-surface-400">Pode adicionar mais médicos depois</p>
                </div>
              </div>

              {error && (
                <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700 mb-4">
                  <AlertCircle size={15} className="mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <Label>Nome completo *</Label>
                  <input
                    type="text"
                    value={medico.nome}
                    onChange={(e) => fieldMedico("nome", e.target.value)}
                    placeholder="Dr. João Pereira"
                    autoFocus
                    className={inputCls()}
                  />
                </div>

                <div>
                  <Label>Especialidade *</Label>
                  <select
                    value={medico.especialidade}
                    onChange={(e) => fieldMedico("especialidade", e.target.value)}
                    className={inputCls()}
                  >
                    <option value="">Selecionar…</option>
                    {ESPECIALIDADES.map((e) => (
                      <option key={e} value={e}>{e}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <Label>Nº de cédula / registro</Label>
                  <input
                    type="text"
                    value={medico.cedula}
                    onChange={(e) => fieldMedico("cedula", e.target.value)}
                    placeholder={pais === "PT" ? "OMD-00000" : "CRM/SP 000000"}
                    className={inputCls()}
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setStep(3)}
                  className="flex-1 rounded-lg border border-surface-200 px-4 py-2.5 text-sm text-surface-600
                             hover:bg-surface-50 transition-colors"
                >
                  Saltar por agora
                </button>
                <button
                  onClick={handleCriarMedico}
                  disabled={loading}
                  className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5
                             text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-all"
                >
                  {loading ? <><Loader2 size={15} className="animate-spin" />A criar…</> : <>Adicionar <ChevronRight size={15} /></>}
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 3: Concluído ────────────────────────────────────────────── */}
          {step === 3 && (
            <div className="text-center py-4">
              <div className="w-16 h-16 rounded-2xl bg-emerald-50 border border-emerald-100 flex items-center justify-center mx-auto mb-5">
                <CheckCircle2 size={32} className="text-emerald-600" />
              </div>

              <h2 className="text-lg font-bold text-surface-900 mb-2">
                {clinicaNomeForDisplay || "Clínica"} está pronta!
              </h2>
              <p className="text-sm text-surface-500 mb-8 max-w-xs mx-auto">
                A sua clínica está configurada. Pode agora gerir pacientes, consultas, pipeline e muito mais.
              </p>

              <div className="grid grid-cols-3 gap-3 mb-8 text-left">
                {[
                  { emoji: "🗓️", label: "Agenda", desc: "Consultas e horários" },
                  { emoji: "👥", label: "Pacientes", desc: `Registo e ${loc.leiPrivacidade}` },
                  { emoji: "📊", label: "Pipeline", desc: "Funil de conversão" },
                ].map((f) => (
                  <div key={f.label} className="bg-surface-50 rounded-xl p-3 border border-surface-100">
                    <div className="text-xl mb-1">{f.emoji}</div>
                    <p className="text-xs font-semibold text-surface-700">{f.label}</p>
                    <p className="text-xs text-surface-400">{f.desc}</p>
                  </div>
                ))}
              </div>

              <button
                onClick={handleConcluir}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-3
                           text-sm font-semibold text-white hover:bg-brand-700 transition-all"
              >
                Ir para o dashboard <ArrowRight size={15} />
              </button>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-surface-400 mt-6">
          © {new Date().getFullYear()} ClinicFlow
        </p>
      </div>
    </div>
  )
}
