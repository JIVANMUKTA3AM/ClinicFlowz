import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Plus, Pencil, Trash2, X, Loader2, AlertCircle,
  Stethoscope, Phone, Mail, BadgePercent, Clock, ChevronRight,
  type LucideIcon,
} from "lucide-react"
import { medicosService, salasService } from "../services/api"
import type { Medico, Sala } from "../types"

// ─── Weekday schedule ─────────────────────────────────────────────────────────

const DIAS = [
  { key: "seg", label: "Seg" },
  { key: "ter", label: "Ter" },
  { key: "qua", label: "Qua" },
  { key: "qui", label: "Qui" },
  { key: "sex", label: "Sex" },
  { key: "sab", label: "Sáb" },
] as const

type DiaKey = typeof DIAS[number]["key"]

const HORA_OPTIONS = Array.from({ length: 24 }, (_, i) => {
  const h = Math.floor(i / 2) + 8
  const m = (i % 2) * 30
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`
}) // 08:00 … 19:30

// ─── Form ─────────────────────────────────────────────────────────────────────

interface FormState {
  nome: string
  especialidade: string
  cedula: string
  email: string
  telefone: string
  comissao_pct: string
  horarios: Partial<Record<DiaKey, string[]>>
}

const EMPTY_FORM: FormState = {
  nome: "", especialidade: "", cedula: "",
  email: "", telefone: "", comissao_pct: "0",
  horarios: {},
}

function medicoToForm(m: Medico): FormState {
  return {
    nome:         m.nome,
    especialidade: m.especialidade,
    cedula:       m.cedula ?? "",
    email:        m.email ?? "",
    telefone:     m.telefone ?? "",
    comissao_pct: String(m.comissao_pct ?? 0),
    horarios:     (m.horarios_disponiveis ?? {}) as Partial<Record<DiaKey, string[]>>,
  }
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function Medicos() {
  const qc = useQueryClient()

  const [selected, setSelected]   = useState<Medico | null>(null)
  const [modal,    setModal]      = useState<"criar" | "editar" | null>(null)
  const [form,     setForm]       = useState<FormState>(EMPTY_FORM)
  const [errors,   setErrors]     = useState<Partial<Record<keyof FormState, string>>>({})
  const [showInat, setShowInat]   = useState(false)

  // ── Queries ────────────────────────────────────────────────────────────

  const { data: medicos = [], isLoading } = useQuery<Medico[]>({
    queryKey: ["medicos", showInat],
    queryFn: () => medicosService.listar(!showInat),
    staleTime: 30_000,
  })

  const { data: salas = [] } = useQuery<Sala[]>({
    queryKey: ["salas"],
    queryFn: () => salasService.listar(),
    staleTime: 60_000,
  })

  // ── Mutations ──────────────────────────────────────────────────────────

  const criarMut = useMutation({
    mutationFn: (f: FormState) => medicosService.criar(formToPayload(f)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["medicos"] }); closeModal() },
  })

  const editarMut = useMutation({
    mutationFn: (f: FormState) => medicosService.atualizar(selected!.id, formToPayload(f)),
    onSuccess: (updated) => {
      setSelected(updated)
      qc.invalidateQueries({ queryKey: ["medicos"] })
      closeModal()
    },
  })

  const desativarMut = useMutation({
    mutationFn: (id: string) => medicosService.desativar(id),
    onSuccess: () => {
      setSelected(null)
      qc.invalidateQueries({ queryKey: ["medicos"] })
    },
  })

  function formToPayload(f: FormState) {
    return {
      nome:          f.nome,
      especialidade: f.especialidade,
      cedula:        f.cedula || undefined,
      email:         f.email || undefined,
      telefone:      f.telefone || undefined,
      comissao_pct:  parseFloat(f.comissao_pct) || 0,
      horarios_disponiveis: Object.keys(f.horarios).length > 0 ? f.horarios : undefined,
    }
  }

  // ── Modal helpers ──────────────────────────────────────────────────────

  function openCriar() { setForm(EMPTY_FORM); setErrors({}); setModal("criar") }
  function openEditar(m: Medico) { setForm(medicoToForm(m)); setErrors({}); setModal("editar") }
  function closeModal() { setModal(null); setErrors({}) }

  function setField<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((p) => ({ ...p, [k]: v }))
    if (errors[k]) setErrors((e) => ({ ...e, [k]: undefined }))
  }

  function validate(): boolean {
    const e: typeof errors = {}
    if (!form.nome.trim())         e.nome         = "Obrigatório"
    if (!form.especialidade.trim()) e.especialidade = "Obrigatório"
    const pct = parseFloat(form.comissao_pct)
    if (isNaN(pct) || pct < 0 || pct > 100) e.comissao_pct = "Entre 0 e 100"
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    modal === "criar" ? criarMut.mutate(form) : editarMut.mutate(form)
  }

  function toggleSlot(dia: DiaKey, hora: string) {
    setForm((prev) => {
      const slots = prev.horarios[dia] ?? []
      const next  = slots.includes(hora)
        ? slots.filter((h) => h !== hora)
        : [...slots, hora].sort()
      return { ...prev, horarios: { ...prev.horarios, [dia]: next } }
    })
  }

  const isSaving  = criarMut.isPending || editarMut.isPending
  const saveError = (criarMut.error || editarMut.error) as Error | null

  // ─────────────────────────────────────────────────────────────────────

  return (
    <div className="flex gap-5 h-full">

      {/* ── Left: table ──────────────────────────────────────────────────── */}
      <div className={`flex flex-col ${selected ? "w-[420px] shrink-0" : "flex-1"}`}>

        {/* Toolbar */}
        <div className="flex items-center gap-3 mb-4">
          <label className="flex items-center gap-2 text-xs text-surface-500 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showInat}
              onChange={(e) => setShowInat(e.target.checked)}
              className="accent-brand-600"
            />
            Mostrar inativos
          </label>
          <div className="ml-auto">
            <button
              onClick={openCriar}
              className="flex items-center gap-1.5 bg-brand-600 text-white text-sm font-medium
                         px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors"
            >
              <Plus size={14} />
              Novo médico
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-surface-100 shadow-sm flex-1 flex flex-col overflow-hidden">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 size={22} className="animate-spin text-brand-500" />
            </div>
          ) : medicos.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-surface-400 gap-2">
              <Stethoscope size={28} className="opacity-30" />
              <p className="text-sm">Nenhum médico registado</p>
            </div>
          ) : (
            <div className="overflow-y-auto flex-1">
              <table className="w-full">
                <thead className="sticky top-0 bg-white z-10 border-b border-surface-100">
                  <tr>
                    <Th>Médico</Th>
                    <Th>Especialidade</Th>
                    {!selected && <Th>Comissão</Th>}
                    <Th>Estado</Th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-50">
                  {medicos.map((m) => (
                    <tr
                      key={m.id}
                      onClick={() => setSelected(m)}
                      className={`hover:bg-surface-50 cursor-pointer transition-colors ${
                        selected?.id === m.id ? "bg-brand-50" : ""
                      }`}
                    >
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 rounded-full bg-brand-100 text-brand-700 text-xs font-bold
                                          flex items-center justify-center shrink-0">
                            {m.nome.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-surface-800 truncate max-w-[140px]">{m.nome}</p>
                            <p className="text-xs text-surface-400 font-mono">{m.email ?? "—"}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-sm text-surface-600">{m.especialidade}</td>
                      {!selected && (
                        <td className="px-3 py-3 text-sm text-surface-600">{m.comissao_pct}%</td>
                      )}
                      <td className="px-3 py-3">
                        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                          m.ativo ? "bg-emerald-100 text-emerald-700" : "bg-surface-100 text-surface-500"
                        }`}>
                          {m.ativo ? "Ativo" : "Inativo"}
                        </span>
                      </td>
                      <td className="pr-4">
                        <ChevronRight size={14} className="text-surface-300" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!isLoading && medicos.length > 0 && (
            <div className="border-t border-surface-50 px-5 py-2">
              <p className="text-xs text-surface-400">{medicos.length} médico{medicos.length !== 1 ? "s" : ""}</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Right: detail panel ──────────────────────────────────────────── */}
      {selected && (
        <div className="flex-1 min-w-0 flex flex-col gap-4">

          {/* Info card */}
          <div className="bg-white rounded-xl border border-surface-100 shadow-sm p-5">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-brand-100 text-brand-700 font-bold text-base
                                flex items-center justify-center shrink-0">
                  {selected.nome.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
                </div>
                <div>
                  <h2 className="text-base font-semibold text-surface-800">{selected.nome}</h2>
                  <p className="text-xs text-surface-400">{selected.especialidade}</p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => openEditar(selected)}
                  className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition">
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => { if (confirm(`Desativar ${selected.nome}?`)) desativarMut.mutate(selected.id) }}
                  className="p-1.5 rounded-lg text-surface-400 hover:text-red-600 hover:bg-red-50 transition">
                  <Trash2 size={14} />
                </button>
                <button onClick={() => setSelected(null)}
                  className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition ml-1">
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <InfoItem icon={Phone}       label="Telefone"  value={selected.telefone ?? "—"} />
              <InfoItem icon={Mail}        label="Email"     value={selected.email ?? "—"} />
              <InfoItem icon={BadgePercent} label="Comissão" value={`${selected.comissao_pct}%`} />
              {selected.cedula && (
                <InfoItem icon={Stethoscope} label="Cédula" value={selected.cedula} />
              )}
            </div>
          </div>

          {/* Horários */}
          {selected.horarios_disponiveis && Object.keys(selected.horarios_disponiveis).length > 0 && (
            <div className="bg-white rounded-xl border border-surface-100 shadow-sm p-5">
              <div className="flex items-center gap-2 mb-3">
                <Clock size={14} className="text-surface-400" />
                <h3 className="text-sm font-semibold text-surface-800">Horários disponíveis</h3>
              </div>
              <div className="space-y-2">
                {DIAS.map(({ key, label }) => {
                  const slots = (selected.horarios_disponiveis as Record<string, string[]>)?.[key] ?? []
                  if (slots.length === 0) return null
                  return (
                    <div key={key} className="flex items-start gap-3">
                      <span className="text-xs font-medium text-surface-500 w-7 pt-0.5">{label}</span>
                      <div className="flex flex-wrap gap-1">
                        {slots.map((h) => (
                          <span key={h} className="text-xs bg-brand-50 text-brand-700 px-2 py-0.5 rounded font-mono">
                            {h}
                          </span>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Salas disponíveis (read-only reference) */}
          <div className="bg-white rounded-xl border border-surface-100 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-surface-800 mb-3">Salas da clínica</h3>
            {salas.length === 0 ? (
              <p className="text-xs text-surface-400">Nenhuma sala registada.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {salas.map((s) => (
                  <span key={s.id}
                    className="text-xs bg-surface-100 text-surface-600 px-3 py-1.5 rounded-lg font-medium">
                    {s.nome}
                    {s.descricao && <span className="opacity-60 ml-1">· {s.descricao}</span>}
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-surface-400 mt-3">
              A associação médico → sala ocorre ao criar cada consulta.
            </p>
          </div>
        </div>
      )}

      {/* ── Modal ────────────────────────────────────────────────────────── */}
      {modal && (
        <Modal
          title={modal === "criar" ? "Novo médico" : "Editar médico"}
          onClose={closeModal}
        >
          <div className="space-y-4">
            {saveError && <ErrorBanner msg={saveError.message} />}

            <div className="grid grid-cols-2 gap-3">
              <Field label="Nome *" error={errors.nome} className="col-span-2">
                <input value={form.nome} onChange={(e) => setField("nome", e.target.value)}
                  placeholder="Dr. João Ferreira" className={iCls(!!errors.nome)} />
              </Field>

              <Field label="Especialidade *" error={errors.especialidade}>
                <input value={form.especialidade} onChange={(e) => setField("especialidade", e.target.value)}
                  placeholder="Medicina Geral" className={iCls(!!errors.especialidade)} />
              </Field>

              <Field label="Cédula">
                <input value={form.cedula} onChange={(e) => setField("cedula", e.target.value)}
                  placeholder="12345" className={iCls(false)} />
              </Field>

              <Field label="Email">
                <input type="email" value={form.email} onChange={(e) => setField("email", e.target.value)}
                  placeholder="dr@clinica.pt" className={iCls(false)} />
              </Field>

              <Field label="Telefone">
                <input value={form.telefone} onChange={(e) => setField("telefone", e.target.value)}
                  placeholder="+351 912 345 678" className={iCls(false)} />
              </Field>

              <Field label="Comissão (%)" error={errors.comissao_pct}>
                <input type="number" min={0} max={100} step={1}
                  value={form.comissao_pct} onChange={(e) => setField("comissao_pct", e.target.value)}
                  className={iCls(!!errors.comissao_pct)} />
              </Field>
            </div>

            {/* Horários disponíveis */}
            <div>
              <p className="text-xs font-medium text-surface-700 mb-2">Horários disponíveis</p>
              <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                {DIAS.map(({ key, label }) => (
                  <div key={key} className="flex items-start gap-2">
                    <span className="text-xs font-medium text-surface-500 w-7 pt-2 shrink-0">{label}</span>
                    <div className="flex flex-wrap gap-1">
                      {HORA_OPTIONS.map((h) => {
                        const active = (form.horarios[key] ?? []).includes(h)
                        return (
                          <button
                            key={h}
                            type="button"
                            onClick={() => toggleSlot(key, h)}
                            className={`text-xs px-2 py-1 rounded font-mono transition-colors ${
                              active
                                ? "bg-brand-600 text-white"
                                : "bg-surface-100 text-surface-500 hover:bg-surface-200"
                            }`}
                          >
                            {h}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <ModalFooter onClose={closeModal} onSubmit={handleSubmit}
            isSaving={isSaving} label={modal === "criar" ? "Criar médico" : "Guardar"} />
        </Modal>
      )}
    </div>
  )
}

// ─── Small components ─────────────────────────────────────────────────────────

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="text-left text-xs font-medium text-surface-400 uppercase tracking-wider px-5 py-3">
      {children}
    </th>
  )
}

function InfoItem({ icon: Icon, label, value }: {
  icon: LucideIcon
  label: string; value: string
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

function Field({ label, error, children, className = "" }: {
  label?: string; error?: string; children: React.ReactNode; className?: string
}) {
  return (
    <div className={`space-y-1 ${className}`}>
      {label && <label className="block text-xs font-medium text-surface-700">{label}</label>}
      {children}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

function iCls(err: boolean) {
  return `w-full rounded-lg border ${err ? "border-red-300 bg-red-50" : "border-surface-200 bg-surface-50"}
    px-3.5 py-2.5 text-sm text-surface-900 placeholder-surface-400
    focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition`
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
      <AlertCircle size={15} className="mt-0.5 shrink-0" /> {msg}
    </div>
  )
}

function ModalFooter({ onClose, onSubmit, isSaving, label }: {
  onClose: () => void; onSubmit: () => void; isSaving: boolean; label: string
}) {
  return (
    <div className="flex justify-end gap-3 mt-6 pt-5 border-t border-surface-100">
      <button onClick={onClose}
        className="px-4 py-2 text-sm rounded-lg border border-surface-200 text-surface-600 hover:bg-surface-50 transition-colors">
        Cancelar
      </button>
      <button onClick={onSubmit} disabled={isSaving}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 transition-colors">
        {isSaving && <Loader2 size={14} className="animate-spin" />}
        {label}
      </button>
    </div>
  )
}

function Modal({ title, onClose, children }: {
  title: string; onClose: () => void; children: React.ReactNode
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", h)
    return () => window.removeEventListener("keydown", h)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-xl max-h-[92vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-100 sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <Stethoscope size={16} className="text-brand-600" />
            <h2 className="text-base font-semibold text-surface-800">{title}</h2>
          </div>
          <button onClick={onClose}
            className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition">
            <X size={16} />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}
