import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { format } from "date-fns"
import { ptBR, pt } from "date-fns/locale"
import {
  Search, Plus, ChevronRight, Phone, Mail, Tag,
  MessageSquare, Calendar, FileText, CheckCircle, Circle,
  ArrowRight, X, Pencil, Trash2, Loader2, AlertCircle,
  type LucideIcon,
} from "lucide-react"
import { pacientesService, timelineService } from "../services/api"
import { useAuthStore } from "../store/authStore"
import type { Paciente, PacienteStatus, PacienteOrigem, Interacao } from "../types"

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<PacienteStatus, string> = {
  lead:      "bg-slate-100 text-slate-600",
  ativo:     "bg-emerald-100 text-emerald-700",
  inativo:   "bg-orange-100 text-orange-700",
  arquivado: "bg-red-100 text-red-600",
}

const ORIGEM_LABEL: Record<PacienteOrigem, string> = {
  whatsapp:  "WhatsApp",
  site:      "Site",
  indicacao: "Indicação",
  balcao:    "Balcão",
}

const TIMELINE_ICON: Record<string, typeof MessageSquare> = {
  whatsapp: MessageSquare,
  consulta: Calendar,
  nota:     FileText,
  lembrete: CheckCircle,
}

const CAMPOS_OBRIGATORIOS = ["nome", "telefone"] as const

// ─── Types ────────────────────────────────────────────────────────────────────

interface FormState {
  nome: string
  telefone: string
  email: string
  documento_fiscal: string
  origem: PacienteOrigem
  status: PacienteStatus
  notas: string
  consentimento_privacidade: boolean
}

const FORM_EMPTY: FormState = {
  nome: "",
  telefone: "",
  email: "",
  documento_fiscal: "",
  origem: "balcao",
  status: "lead",
  notas: "",
  consentimento_privacidade: false,
}

function pacienteToForm(p: Paciente): FormState {
  return {
    nome: p.nome,
    telefone: p.telefone,
    email: p.email ?? "",
    documento_fiscal: p.documento_fiscal ?? "",
    origem: p.origem,
    status: p.status,
    notas: p.notas ?? "",
    consentimento_privacidade: true,
  }
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function Pacientes() {
  const qc   = useQueryClient()
  const pais = useAuthStore((s) => s.user?.pais ?? "PT")
  const dateFnsLocale = pais === "PT" ? pt : ptBR

  const [search,       setSearch]       = useState("")
  const [statusFiltro, setStatusFiltro] = useState<PacienteStatus | "">("")
  const [selected,     setSelected]     = useState<Paciente | null>(null)
  const [novaNota,     setNovaNota]     = useState("")

  // Modal state
  const [modal, setModal] = useState<"criar" | "editar" | null>(null)
  const [form,  setForm]  = useState<FormState>(FORM_EMPTY)
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof FormState, string>>>({})

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data: pacientes = [], isLoading } = useQuery({
    queryKey: ["pacientes", search, statusFiltro],
    queryFn: () =>
      pacientesService.listar({
        ...(search       ? { q: search }             : {}),
        ...(statusFiltro ? { status: statusFiltro }  : {}),
      }),
    staleTime: 30_000,
  })

  const { data: timeline = [] } = useQuery<Interacao[]>({
    queryKey: ["timeline", selected?.id],
    queryFn: () => timelineService.paciente(selected!.id),
    enabled: !!selected,
  })

  // ── Mutations ─────────────────────────────────────────────────────────────

  const criarMutation = useMutation({
    mutationFn: (data: FormState) =>
      pacientesService.criar({
        nome:                     data.nome,
        telefone:                 data.telefone,
        email:                    data.email              || undefined,
        documento_fiscal:         data.documento_fiscal   || undefined,
        origem:                   data.origem,
        status:                   data.status,
        notas:                    data.notas              || undefined,
        consentimento_privacidade: data.consentimento_privacidade,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pacientes"] })
      closeModal()
    },
  })

  const editarMutation = useMutation({
    mutationFn: (data: FormState) =>
      pacientesService.atualizar(selected!.id, {
        nome:     data.nome,
        telefone: data.telefone,
        email:    data.email    || undefined,
        status:   data.status,
        notas:    data.notas    || undefined,
      }),
    onSuccess: (updated) => {
      setSelected(updated)
      qc.invalidateQueries({ queryKey: ["pacientes"] })
      closeModal()
    },
  })

  const arquivarMutation = useMutation({
    mutationFn: (id: string) => pacientesService.atualizar(id, { status: "arquivado" }),
    onSuccess: () => {
      setSelected(null)
      qc.invalidateQueries({ queryKey: ["pacientes"] })
    },
  })

  const atualizarStatusMutation = useMutation({
    mutationFn: (status: PacienteStatus) =>
      pacientesService.atualizar(selected!.id, { status }),
    onSuccess: (updated) => {
      setSelected(updated)
      qc.invalidateQueries({ queryKey: ["pacientes"] })
    },
  })

  const addNotaMutation = useMutation({
    mutationFn: () =>
      timelineService.criar({
        paciente_id: selected!.id,
        tipo: "nota",
        conteudo: novaNota,
        criado_por: "recepcao",
      }),
    onSuccess: () => {
      setNovaNota("")
      qc.invalidateQueries({ queryKey: ["timeline", selected?.id] })
    },
  })

  // ── Modal helpers ─────────────────────────────────────────────────────────

  function openCriar() {
    setForm(FORM_EMPTY)
    setFormErrors({})
    setModal("criar")
  }

  function openEditar(p: Paciente) {
    setForm(pacienteToForm(p))
    setFormErrors({})
    setModal("editar")
  }

  function closeModal() {
    setModal(null)
    setFormErrors({})
  }

  function handleField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    if (formErrors[key]) setFormErrors((e) => ({ ...e, [key]: undefined }))
  }

  function validate(): boolean {
    const erros: Partial<Record<keyof FormState, string>> = {}
    if (!form.nome.trim())     erros.nome     = "Obrigatório"
    if (!form.telefone.trim()) erros.telefone = "Obrigatório"
    if (modal === "criar" && !form.consentimento_privacidade)
      erros.consentimento_privacidade = "Consentimento de privacidade obrigatório"
    setFormErrors(erros)
    return Object.keys(erros).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    if (modal === "criar") criarMutation.mutate(form)
    else                   editarMutation.mutate(form)
  }

  const isSaving = criarMutation.isPending || editarMutation.isPending
  const saveError = (criarMutation.error || editarMutation.error) as Error | null

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex gap-5 h-full">

      {/* ── Left: list ─────────────────────────────────────────────────────── */}
      <div className={`flex flex-col min-w-0 ${selected ? "w-[420px] shrink-0" : "flex-1"}`}>

        {/* Toolbar */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400 pointer-events-none" />
            <input
              type="text"
              placeholder="Pesquisar por nome ou telefone…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm border border-surface-200 rounded-lg bg-white
                         focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition"
            />
          </div>

          <select
            value={statusFiltro}
            onChange={(e) => setStatusFiltro(e.target.value as PacienteStatus | "")}
            className="text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white text-surface-600
                       focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition"
          >
            <option value="">Todos</option>
            <option value="lead">Lead</option>
            <option value="ativo">Ativo</option>
            <option value="inativo">Inativo</option>
            <option value="arquivado">Arquivado</option>
          </select>

          <button
            onClick={openCriar}
            className="flex items-center gap-1.5 bg-brand-600 text-white text-sm font-medium px-4 py-2
                       rounded-lg hover:bg-brand-700 transition-colors shrink-0"
          >
            <Plus size={14} />
            Novo paciente
          </button>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-surface-100 shadow-sm overflow-hidden flex-1 flex flex-col">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 size={24} className="animate-spin text-brand-500" />
            </div>
          ) : pacientes.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-surface-400 gap-2">
              <Search size={28} className="opacity-40" />
              <p className="text-sm">Nenhum paciente encontrado</p>
            </div>
          ) : (
            <div className="overflow-y-auto flex-1">
              <table className="w-full">
                <thead className="sticky top-0 bg-white z-10">
                  <tr className="border-b border-surface-100">
                    <th className="text-left text-xs font-medium text-surface-400 uppercase tracking-wider px-5 py-3">Paciente</th>
                    <th className="text-left text-xs font-medium text-surface-400 uppercase tracking-wider px-3 py-3">Telefone</th>
                    {!selected && (
                      <th className="text-left text-xs font-medium text-surface-400 uppercase tracking-wider px-3 py-3">Origem</th>
                    )}
                    <th className="text-left text-xs font-medium text-surface-400 uppercase tracking-wider px-3 py-3">Status</th>
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-50">
                  {pacientes.map((p) => (
                    <tr
                      key={p.id}
                      onClick={() => setSelected(p)}
                      className={`hover:bg-surface-50 cursor-pointer transition-colors ${
                        selected?.id === p.id ? "bg-brand-50" : ""
                      }`}
                    >
                      <td className="px-5 py-3">
                        <p className="text-sm font-medium text-surface-800 truncate">{p.nome}</p>
                        <p className="text-xs text-surface-400 truncate">{p.email || "—"}</p>
                      </td>
                      <td className="px-3 py-3 text-sm text-surface-500 font-mono whitespace-nowrap">{p.telefone}</td>
                      {!selected && (
                        <td className="px-3 py-3 text-xs text-surface-400">{ORIGEM_LABEL[p.origem]}</td>
                      )}
                      <td className="px-3 py-3">
                        <StatusBadge status={p.status} />
                      </td>
                      <td className="pr-4 py-3">
                        <ChevronRight size={14} className="text-surface-300" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Footer count */}
          {!isLoading && pacientes.length > 0 && (
            <div className="border-t border-surface-50 px-5 py-2.5">
              <p className="text-xs text-surface-400">{pacientes.length} paciente{pacientes.length !== 1 ? "s" : ""}</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Right: detail panel ────────────────────────────────────────────── */}
      {selected && (
        <div className="flex-1 min-w-0 flex flex-col gap-4">

          {/* Info card */}
          <div className="bg-white rounded-xl border border-surface-100 shadow-sm p-5">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-surface-800">{selected.nome}</h2>
                <p className="text-xs text-surface-400 mt-0.5">
                  {ORIGEM_LABEL[selected.origem]} · desde {format(new Date(selected.created_at), "MMM yyyy", { locale: dateFnsLocale })}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => openEditar(selected)}
                  title="Editar"
                  className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => {
                    if (confirm(`Arquivar ${selected.nome}?`)) arquivarMutation.mutate(selected.id)
                  }}
                  title="Arquivar"
                  className="p-1.5 rounded-lg text-surface-400 hover:text-red-600 hover:bg-red-50 transition"
                >
                  <Trash2 size={14} />
                </button>
                <button
                  onClick={() => setSelected(null)}
                  className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition ml-1"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Info grid */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <InfoItem icon={Phone} label="Telefone" value={selected.telefone} />
              <InfoItem icon={Mail}  label="Email"    value={selected.email || "—"} />
              <InfoItem
                icon={CheckCircle}
                label="Privacidade"
                value={
                  selected.consentimento_privacidade_at
                    ? `✓ ${format(new Date(selected.consentimento_privacidade_at), "dd/MM/yyyy")}`
                    : "⚠ Sem consentimento"
                }
              />
              {selected.tags.length > 0 && (
                <div className="flex items-start gap-2 col-span-2">
                  <Tag size={13} className="text-surface-400 mt-0.5 shrink-0" />
                  <div className="flex flex-wrap gap-1">
                    {selected.tags.map((t) => (
                      <span key={t} className="text-xs bg-surface-100 text-surface-600 px-2 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Status switcher */}
            <div className="mt-4 pt-4 border-t border-surface-50 flex gap-2 flex-wrap">
              {(["lead", "ativo", "inativo"] as PacienteStatus[]).map((s) => (
                <button
                  key={s}
                  onClick={() => atualizarStatusMutation.mutate(s)}
                  disabled={atualizarStatusMutation.isPending}
                  className={`text-xs px-3 py-1.5 rounded-lg border capitalize transition-colors ${
                    selected.status === s
                      ? "border-brand-500 bg-brand-50 text-brand-700 font-medium"
                      : "border-surface-200 text-surface-500 hover:border-surface-300 hover:bg-surface-50"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Timeline */}
          <div className="bg-white rounded-xl border border-surface-100 shadow-sm flex-1 flex flex-col overflow-hidden">
            <div className="px-5 py-3 border-b border-surface-50">
              <h3 className="text-sm font-medium text-surface-800">Timeline</h3>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
              {timeline.map((item) => {
                const Icon = TIMELINE_ICON[item.tipo] ?? Circle
                return (
                  <div key={item.id} className="flex gap-3">
                    <div className="w-6 h-6 rounded-full bg-surface-100 flex items-center justify-center shrink-0 mt-0.5">
                      <Icon size={12} className="text-surface-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs font-medium text-surface-600 capitalize">{item.tipo}</span>
                        {item.direcao && (
                          <span className={`text-xs ${item.direcao === "entrada" ? "text-blue-500" : "text-emerald-500"}`}>
                            {item.direcao === "entrada" ? "← entrada" : "→ saída"}
                          </span>
                        )}
                        <span className="text-xs text-surface-300 ml-auto shrink-0">
                          {format(new Date(item.created_at), "dd/MM HH:mm")}
                        </span>
                      </div>
                      <p className="text-sm text-surface-600 leading-snug">{item.conteudo}</p>
                    </div>
                  </div>
                )
              })}
              {timeline.length === 0 && (
                <p className="text-sm text-surface-400 text-center py-8">Sem interações ainda.</p>
              )}
            </div>

            {/* Note input */}
            <div className="px-4 py-3 border-t border-surface-100 flex gap-2">
              <input
                type="text"
                placeholder="Adicionar nota…"
                value={novaNota}
                onChange={(e) => setNovaNota(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && novaNota.trim() && addNotaMutation.mutate()}
                className="flex-1 text-sm border border-surface-200 rounded-lg px-3 py-2
                           focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition"
              />
              <button
                onClick={() => novaNota.trim() && addNotaMutation.mutate()}
                disabled={!novaNota.trim() || addNotaMutation.isPending}
                className="bg-brand-600 text-white px-3 py-2 rounded-lg hover:bg-brand-700
                           disabled:opacity-40 transition-colors"
              >
                {addNotaMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: criar / editar ───────────────────────────────────────────── */}
      {modal && (
        <Modal
          title={modal === "criar" ? "Novo paciente" : "Editar paciente"}
          onClose={closeModal}
        >
          <div className="space-y-4">
            {saveError && (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
                <AlertCircle size={15} className="mt-0.5 shrink-0" />
                {saveError.message}
              </div>
            )}

            {/* Nome */}
            <Field label="Nome *" error={formErrors.nome}>
              <input
                type="text"
                value={form.nome}
                onChange={(e) => handleField("nome", e.target.value)}
                placeholder="Maria Silva"
                className={inputCls(!!formErrors.nome)}
              />
            </Field>

            {/* Telefone */}
            <Field label="Telefone *" error={formErrors.telefone}>
              <input
                type="tel"
                value={form.telefone}
                onChange={(e) => handleField("telefone", e.target.value)}
                placeholder="+351 912 345 678"
                className={inputCls(!!formErrors.telefone)}
              />
            </Field>

            {/* Email */}
            <Field label="Email">
              <input
                type="email"
                value={form.email}
                onChange={(e) => handleField("email", e.target.value)}
                placeholder="maria@exemplo.pt"
                className={inputCls(false)}
              />
            </Field>

            {/* Documento fiscal */}
            <Field label="Documento fiscal">
              <input
                type="text"
                value={form.documento_fiscal}
                onChange={(e) => handleField("documento_fiscal", e.target.value)}
                placeholder="—"
                className={inputCls(false)}
              />
            </Field>

            {/* Origem + Status (row) */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Origem">
                <select
                  value={form.origem}
                  onChange={(e) => handleField("origem", e.target.value as PacienteOrigem)}
                  className={inputCls(false)}
                >
                  {(Object.entries(ORIGEM_LABEL) as [PacienteOrigem, string][]).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </Field>

              <Field label="Status">
                <select
                  value={form.status}
                  onChange={(e) => handleField("status", e.target.value as PacienteStatus)}
                  className={inputCls(false)}
                >
                  <option value="lead">Lead</option>
                  <option value="ativo">Ativo</option>
                  <option value="inativo">Inativo</option>
                </select>
              </Field>
            </div>

            {/* Notas */}
            <Field label="Notas">
              <textarea
                value={form.notas}
                onChange={(e) => handleField("notas", e.target.value)}
                placeholder="Observações sobre o paciente…"
                rows={3}
                className={`${inputCls(false)} resize-none`}
              />
            </Field>

            {/* Consentimento privacidade — only on create */}
            {modal === "criar" && (
              <Field error={formErrors.consentimento_privacidade}>
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.consentimento_privacidade}
                    onChange={(e) => handleField("consentimento_privacidade", e.target.checked)}
                    className="mt-0.5 accent-brand-600"
                  />
                  <span className="text-sm text-surface-700">
                    Paciente deu consentimento para tratamento de dados pessoais
                    <span className="text-red-500 ml-1">*</span>
                  </span>
                </label>
              </Field>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 mt-6 pt-5 border-t border-surface-100">
            <button
              onClick={closeModal}
              className="px-4 py-2 text-sm rounded-lg border border-surface-200 text-surface-600
                         hover:bg-surface-50 transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg
                         bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {isSaving && <Loader2 size={14} className="animate-spin" />}
              {modal === "criar" ? "Criar paciente" : "Guardar alterações"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ─── Small components ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: PacienteStatus }) {
  return (
    <span className={`text-xs px-2.5 py-1 rounded-full font-medium capitalize ${STATUS_BADGE[status]}`}>
      {status}
    </span>
  )
}

function InfoItem({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon
  label: string
  value: string
}) {
  return (
    <div className="flex items-start gap-2">
      <Icon size={13} className="text-surface-400 mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="text-xs text-surface-400">{label}</p>
        <p className="text-sm text-surface-700 truncate">{value}</p>
      </div>
    </div>
  )
}

function Field({
  label,
  error,
  children,
}: {
  label?: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1">
      {label && (
        <label className="block text-xs font-medium text-surface-700">{label}</label>
      )}
      {children}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

function inputCls(hasError: boolean) {
  return `w-full rounded-lg border ${
    hasError ? "border-red-300 bg-red-50" : "border-surface-200 bg-surface-50"
  } px-3.5 py-2.5 text-sm text-surface-900 placeholder-surface-400
  focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition`
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  // Close on Escape
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

      {/* Panel */}
      <div
        ref={ref}
        className="relative bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-100">
          <h2 className="text-base font-semibold text-surface-800">{title}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}
