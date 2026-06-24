import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Plus, Pencil, Trash2, X, Loader2, AlertCircle,
  DoorOpen, ChevronRight, Stethoscope,
} from "lucide-react"
import { salasService, medicosService, consultasService } from "../services/api"
import type { Sala, Medico, Consulta } from "../types"

// ─── Form ─────────────────────────────────────────────────────────────────────

interface FormState { nome: string; descricao: string }
const EMPTY: FormState = { nome: "", descricao: "" }

// ─── Page ─────────────────────────────────────────────────────────────────────

export function Salas() {
  const qc = useQueryClient()

  const [selected,  setSelected]  = useState<Sala | null>(null)
  const [modal,     setModal]     = useState<"criar" | "editar" | null>(null)
  const [form,      setForm]      = useState<FormState>(EMPTY)
  const [errors,    setErrors]    = useState<Partial<Record<keyof FormState, string>>>({})
  const [showInat,  setShowInat]  = useState(false)

  // ── Queries ────────────────────────────────────────────────────────────

  const { data: salas = [], isLoading } = useQuery<Sala[]>({
    queryKey: ["salas", showInat],
    queryFn: () => salasService.listar(!showInat),
    staleTime: 30_000,
  })

  const { data: medicos = [] } = useQuery<Medico[]>({
    queryKey: ["medicos", false],
    queryFn: () => medicosService.listar(false),
    staleTime: 60_000,
  })

  // Recent consultations in selected room — to show which doctors use it
  const { data: consultasSala = [] } = useQuery<Consulta[]>({
    queryKey: ["consultas-sala", selected?.id],
    queryFn: () =>
      consultasService.listar({ sala_id: selected!.id, limit: "20" }),
    enabled: !!selected,
    staleTime: 60_000,
  })

  // Derive doctors who have used this room
  const medicosSala = (() => {
    const ids = new Set(consultasSala.map((c) => c.medico_id))
    return medicos.filter((m) => ids.has(m.id))
  })()

  // ── Mutations ──────────────────────────────────────────────────────────

  const criarMut = useMutation({
    mutationFn: (f: FormState) => salasService.criar({ nome: f.nome, descricao: f.descricao || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["salas"] }); closeModal() },
  })

  const editarMut = useMutation({
    mutationFn: (f: FormState) =>
      salasService.atualizar(selected!.id, { nome: f.nome, descricao: f.descricao || undefined }),
    onSuccess: (updated) => {
      setSelected(updated)
      qc.invalidateQueries({ queryKey: ["salas"] })
      closeModal()
    },
  })

  const desativarMut = useMutation({
    mutationFn: (id: string) => salasService.desativar(id),
    onSuccess: () => { setSelected(null); qc.invalidateQueries({ queryKey: ["salas"] }) },
  })

  // ── Modal helpers ──────────────────────────────────────────────────────

  function openCriar() { setForm(EMPTY); setErrors({}); setModal("criar") }
  function openEditar(s: Sala) {
    setForm({ nome: s.nome, descricao: s.descricao ?? "" })
    setErrors({})
    setModal("editar")
  }
  function closeModal() { setModal(null); setErrors({}) }

  function setField<K extends keyof FormState>(k: K, v: string) {
    setForm((p) => ({ ...p, [k]: v }))
    if (errors[k]) setErrors((e) => ({ ...e, [k]: undefined }))
  }

  function validate(): boolean {
    const e: typeof errors = {}
    if (!form.nome.trim()) e.nome = "Obrigatório"
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    modal === "criar" ? criarMut.mutate(form) : editarMut.mutate(form)
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
            <input type="checkbox" checked={showInat}
              onChange={(e) => setShowInat(e.target.checked)} className="accent-brand-600" />
            Mostrar inativas
          </label>
          <div className="ml-auto">
            <button onClick={openCriar}
              className="flex items-center gap-1.5 bg-brand-600 text-white text-sm font-medium
                         px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors">
              <Plus size={14} />
              Nova sala
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-surface-100 shadow-sm flex-1 flex flex-col overflow-hidden">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 size={22} className="animate-spin text-brand-500" />
            </div>
          ) : salas.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-surface-400 gap-2">
              <DoorOpen size={28} className="opacity-30" />
              <p className="text-sm">Nenhuma sala registada</p>
            </div>
          ) : (
            <div className="overflow-y-auto flex-1">
              <table className="w-full">
                <thead className="sticky top-0 bg-white z-10 border-b border-surface-100">
                  <tr>
                    <Th>Sala</Th>
                    <Th>Descrição</Th>
                    <Th>Estado</Th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-50">
                  {salas.map((s) => (
                    <tr key={s.id} onClick={() => setSelected(s)}
                      className={`hover:bg-surface-50 cursor-pointer transition-colors ${
                        selected?.id === s.id ? "bg-brand-50" : ""
                      }`}>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                            s.ativa ? "bg-brand-100 text-brand-700" : "bg-surface-100 text-surface-400"
                          }`}>
                            <DoorOpen size={14} />
                          </div>
                          <p className="text-sm font-semibold text-surface-800">{s.nome}</p>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-sm text-surface-500 truncate max-w-[200px]">
                        {s.descricao ?? "—"}
                      </td>
                      <td className="px-3 py-3">
                        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                          s.ativa ? "bg-emerald-100 text-emerald-700" : "bg-surface-100 text-surface-500"
                        }`}>
                          {s.ativa ? "Ativa" : "Inativa"}
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
          {!isLoading && salas.length > 0 && (
            <div className="border-t border-surface-50 px-5 py-2">
              <p className="text-xs text-surface-400">
                {salas.filter((s) => s.ativa).length} ativa{salas.filter((s) => s.ativa).length !== 1 ? "s" : ""}
                {" / "}{salas.length} total
              </p>
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
                <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${
                  selected.ativa ? "bg-brand-100 text-brand-700" : "bg-surface-100 text-surface-400"
                }`}>
                  <DoorOpen size={20} />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-surface-800">{selected.nome}</h2>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    selected.ativa ? "bg-emerald-100 text-emerald-700" : "bg-surface-100 text-surface-500"
                  }`}>
                    {selected.ativa ? "Ativa" : "Inativa"}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => openEditar(selected)}
                  className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition">
                  <Pencil size={14} />
                </button>
                {selected.ativa && (
                  <button
                    onClick={() => { if (confirm(`Desativar sala "${selected.nome}"?`)) desativarMut.mutate(selected.id) }}
                    className="p-1.5 rounded-lg text-surface-400 hover:text-red-600 hover:bg-red-50 transition">
                    <Trash2 size={14} />
                  </button>
                )}
                <button onClick={() => setSelected(null)}
                  className="p-1.5 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition ml-1">
                  <X size={14} />
                </button>
              </div>
            </div>

            {selected.descricao && (
              <p className="text-sm text-surface-600 bg-surface-50 rounded-lg px-4 py-3 leading-relaxed">
                {selected.descricao}
              </p>
            )}
          </div>

          {/* Médicos associados (via consultas) */}
          <div className="bg-white rounded-xl border border-surface-100 shadow-sm p-5 flex-1">
            <div className="flex items-center gap-2 mb-3">
              <Stethoscope size={14} className="text-surface-400" />
              <h3 className="text-sm font-semibold text-surface-800">Médicos que utilizam esta sala</h3>
            </div>

            {medicosSala.length === 0 ? (
              <p className="text-xs text-surface-400">
                Nenhum médico com consultas registadas nesta sala.
              </p>
            ) : (
              <div className="space-y-2">
                {medicosSala.map((m) => (
                  <div key={m.id}
                    className="flex items-center gap-3 px-3 py-2.5 bg-surface-50 rounded-xl">
                    <div className="w-8 h-8 rounded-full bg-brand-100 text-brand-700 text-xs font-bold
                                    flex items-center justify-center shrink-0">
                      {m.nome.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-surface-800 truncate">{m.nome}</p>
                      <p className="text-xs text-surface-400">{m.especialidade}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* All medicos (for assignment reference) */}
            {medicosSala.length < medicos.length && medicos.length > 0 && (
              <>
                <p className="text-xs font-medium text-surface-400 mt-4 mb-2">Outros médicos da clínica</p>
                <div className="flex flex-wrap gap-2">
                  {medicos
                    .filter((m) => !medicosSala.find((ms) => ms.id === m.id))
                    .map((m) => (
                      <span key={m.id}
                        className="text-xs bg-surface-100 text-surface-500 px-2.5 py-1 rounded-lg">
                        {m.nome}
                      </span>
                    ))}
                </div>
                <p className="text-xs text-surface-400 mt-2">
                  Para associar, seleccione esta sala ao criar uma consulta na Agenda.
                </p>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Modal ────────────────────────────────────────────────────────── */}
      {modal && (
        <Modal title={modal === "criar" ? "Nova sala" : "Editar sala"} onClose={closeModal}>
          <div className="space-y-4">
            {saveError && (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
                <AlertCircle size={15} className="mt-0.5 shrink-0" /> {saveError.message}
              </div>
            )}

            <Field label="Nome *" error={errors.nome}>
              <input value={form.nome} onChange={(e) => setField("nome", e.target.value)}
                placeholder="Sala 1 / Consultório A"
                className={iCls(!!errors.nome)} />
            </Field>

            <Field label="Descrição">
              <textarea
                value={form.descricao}
                onChange={(e) => setField("descricao", e.target.value)}
                rows={3}
                placeholder="Ex: Sala de Radiologia, piso 2…"
                className={`${iCls(false)} resize-none`}
              />
            </Field>
          </div>

          <div className="flex justify-end gap-3 mt-6 pt-5 border-t border-surface-100">
            <button onClick={closeModal}
              className="px-4 py-2 text-sm rounded-lg border border-surface-200 text-surface-600 hover:bg-surface-50 transition-colors">
              Cancelar
            </button>
            <button onClick={handleSubmit} disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 transition-colors">
              {isSaving && <Loader2 size={14} className="animate-spin" />}
              {modal === "criar" ? "Criar sala" : "Guardar"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ─── Shared helpers ───────────────────────────────────────────────────────────

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="text-left text-xs font-medium text-surface-400 uppercase tracking-wider px-5 py-3">
      {children}
    </th>
  )
}

function Field({ label, error, children }: {
  label?: string; error?: string; children: React.ReactNode
}) {
  return (
    <div className="space-y-1">
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
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-100 sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <DoorOpen size={16} className="text-brand-600" />
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
