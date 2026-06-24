import { FormEvent, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Stethoscope, Loader2, AlertCircle, CheckCircle2 } from "lucide-react"
import { supabase } from "../lib/supabase"

export function Register() {
  const navigate = useNavigate()

  const [nome,            setNome]            = useState("")
  const [email,           setEmail]           = useState("")
  const [password,        setPassword]        = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [loading,         setLoading]         = useState(false)
  const [error,           setError]           = useState<string | null>(null)
  const [awaitingEmail,   setAwaitingEmail]   = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (password.length < 8) {
      setError("A palavra-passe deve ter pelo menos 8 caracteres")
      return
    }
    if (password !== confirmPassword) {
      setError("As palavras-passe não coincidem")
      return
    }

    setLoading(true)
    try {
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { nome } },
      })

      if (signUpError) throw signUpError

      if (data.session) {
        // Confirmação de email desactivada — sessão imediata
        navigate("/onboarding", { replace: true })
      } else {
        // Confirmação de email necessária
        setAwaitingEmail(true)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Erro ao criar conta"
      // Traduzir mensagens comuns do Supabase
      if (msg.includes("already registered")) {
        setError("Este email já está registado. Inicie sessão.")
      } else if (msg.includes("weak")) {
        setError("Palavra-passe demasiado fraca.")
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  if (awaitingEmail) {
    return (
      <div className="min-h-screen bg-surface-50 flex items-center justify-center px-4">
        <div className="w-full max-w-sm text-center">
          <div className="w-14 h-14 rounded-2xl bg-emerald-50 border border-emerald-100 flex items-center justify-center mx-auto mb-6">
            <CheckCircle2 size={28} className="text-emerald-600" />
          </div>
          <h1 className="text-xl font-bold text-surface-900 mb-2">Verifique o seu email</h1>
          <p className="text-sm text-surface-500 mb-6">
            Enviámos um link de confirmação para <strong>{email}</strong>.
            Clique no link para activar a sua conta e continuar a configuração.
          </p>
          <Link
            to="/login"
            className="text-sm text-brand-600 hover:text-brand-700 font-medium"
          >
            Voltar ao início de sessão
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-brand-600 flex items-center justify-center mb-4 shadow-lg shadow-brand-600/30">
            <Stethoscope size={22} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-surface-900 tracking-tight">ClinicFlow</h1>
          <p className="text-sm text-surface-500 mt-1">Crie a sua conta gratuita</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-surface-100 p-8">
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>

            {error && (
              <div className="flex items-start gap-2.5 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-surface-700 uppercase tracking-wider">
                Nome
              </label>
              <input
                type="text"
                autoComplete="name"
                required
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Maria Silva"
                className="w-full rounded-lg border border-surface-200 bg-surface-50 px-3.5 py-2.5 text-sm
                           text-surface-900 placeholder-surface-400 focus:outline-none focus:ring-2
                           focus:ring-brand-500 focus:border-transparent transition"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-surface-700 uppercase tracking-wider">
                Email
              </label>
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="clinica@exemplo.pt"
                className="w-full rounded-lg border border-surface-200 bg-surface-50 px-3.5 py-2.5 text-sm
                           text-surface-900 placeholder-surface-400 focus:outline-none focus:ring-2
                           focus:ring-brand-500 focus:border-transparent transition"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-surface-700 uppercase tracking-wider">
                Palavra-passe
              </label>
              <input
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
                className="w-full rounded-lg border border-surface-200 bg-surface-50 px-3.5 py-2.5 text-sm
                           text-surface-900 placeholder-surface-400 focus:outline-none focus:ring-2
                           focus:ring-brand-500 focus:border-transparent transition"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-surface-700 uppercase tracking-wider">
                Confirmar palavra-passe
              </label>
              <input
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-surface-200 bg-surface-50 px-3.5 py-2.5 text-sm
                           text-surface-900 placeholder-surface-400 focus:outline-none focus:ring-2
                           focus:ring-brand-500 focus:border-transparent transition"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !nome || !email || !password || !confirmPassword}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5
                         text-sm font-semibold text-white hover:bg-brand-700 focus:outline-none focus:ring-2
                         focus:ring-brand-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-all mt-2"
            >
              {loading ? (
                <><Loader2 size={15} className="animate-spin" />A criar conta…</>
              ) : (
                "Criar conta"
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-surface-500 mt-5">
          Já tem conta?{" "}
          <Link to="/login" className="text-brand-600 hover:text-brand-700 font-medium">
            Iniciar sessão
          </Link>
        </p>

        <p className="text-center text-xs text-surface-400 mt-4">
          © {new Date().getFullYear()} ClinicFlow · Mercado Portugal
        </p>
      </div>
    </div>
  )
}
