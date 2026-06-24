import { useState, useEffect, useRef, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  format, startOfWeek, addDays, isSameDay, addWeeks, subWeeks,
  parseISO, setHours, setMinutes,
} from "date-fns"
import { ptBR, pt } from "date-fns/locale"
import {
  ChevronLeft, ChevronRight, Plus, X, Loader2, AlertCircle,
  Clock, User, Stethoscope, CheckCircle, XCircle, AlertTriangle,
  Calendar,
} from "lucide-react"
import {
  consultasService, medicosService, pacientesService, agendaService,
} from "../services/api"
import type { CriarConsultaDTO } from "../services/consultas.service"
import { useAuthStore } from "../store/authStore"
import type { Consulta, ConsultaStatus, ConsultaTipo, Medico, Paciente } from "../types"

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUS_PILL: Record<ConsultaStatus, string> = {
  agendada:   "border-l-blue-400   bg-blue-50   text-blue-700",
  confirmada: "border-l-emerald-400 bg-emerald-50 text-emerald-700",
  realizada:  "border-l-slate-300  bg-slate-50  text-slate-500",
  falta:      "border-l-red-400    bg-red-50    text-red-600",
  cancelada:  "border-l-orange-300 bg-orange-50 text-orange-600",
}

const STATUS_BADGE: Record<ConsultaStatus, string> = {
  agendada:   "bg-blue-100 text-blue-700",
  confirmada: "bg-emerald-100 text-emerald-700",
  realizada:  "bg-slate-100 text-slate-600",
  falta:      "bg-red-100 text-red-600",
  cancelada:  "bg-orange-100 text-orange-600",
}

const STATUS_LABEL: Record<ConsultaStatus, string> = {
  agendada:   "Agendada",
  confirmada: "Confirmada",
  realizada:  "Realizada",
  falta:      "Falta",
  cancelada:  "Cancelada",
}

const TIPO_LABEL: Record<ConsultaTipo, string> = {
  primeira_vez: "1ª vez",
  retorno:      "Retorno",
  urgencia:     "Urgência",
  avaliacao:    "Avaliação",
}

const HORAS_DIA = Array.from({ length: 23 }, (_, i) => {
  const h = Math.floor(i / 2) + 8
  const m = (i % 2) * 30
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`
}) // 08:00 … 19:00

const DIAS_SEMANA = 6 // Seg – Sáb

// ─── Types ────────────────────────────────────────────────────────────────────

interface CreateForm {
  paciente_id: string
  paciente_nome: string  // for display only
  medico_id: string
  data: string           // YYYY-MM-DD
  hora: string           // HH:MM
  tipo: ConsultaTipo
  duracao_min: number
  valor: string
  observacoes: string
}

const FORM_EMPTY: CreateForm = {
  paciente_id:  "",
  paciente_nome: "",
  medico_id:    "",
  data:         format(new Date(), "yyyy-MM-dd"),
  hora:         "09:00",
  tipo:         "primeira_vez",
  duracao_min:  30,
  valor:        "",
  observacoes:  "",
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function Agenda() {
  const qc   = useQueryClient()
  const pais = useAuthStore((s) => s.user?.pais ?? "PT")
  const dateFnsLocale = pais === "PT" ? pt : ptBR

  const [semana,       setSemana]       = useState(new Date())
  const [diaSelected,  setDiaSelected]  = useState(new Date())
  const [consultaOpen, setConsultaOpen] = useState<Consulta | null>(null)
  const [modal,        setModal]        = useState(false)
  const [form,         setForm]         = useState<CreateForm>(FORM_EMPTY)
  const [formErrors,   setFormErrors]   = useState<Partial<Record<keyof CreateForm, string>>>({})

  const inicioSemana = startOfWeek(semana, { weekStartsOn: 1 })
  const fimSemana    = addDays(inicioSemana, DIAS_SEMANA - 1)
  const diasSemana   = Array.from({ length: DIAS_SEMANA }, (_, i) => addDays(inicioSemana, i))

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data: consultas = [], isLoading: loadingConsultas } = useQuery<Consulta[]>({
    queryKey: ["consultas-semana", format(inicioSemana, "yyyy-MM-dd")],
    queryFn: () =>
      consultasService.listar({
        data_inicio: format(inicioSemana, "yyyy-MM-dd"),
        data_fim:    format(fimSemana,    "yyyy-MM-dd"),
      }),
    staleTime: 60_000,
  })

  const { data: medicos = [] } = useQuery<Medico[]>({
    queryKey: ["medicos"],
    queryFn: () => medicosService.listar(),
    staleTime: 5 * 60_000,
  })

  const { data: pacientes = [] } = useQuery<Paciente[]>({
    queryKey: ["pacientes", ""],
    queryFn: () => pacientesService.listar(),
    staleTime: 5 * 60_000,
  })

  // Doctor availability — only when medico + date are selected in form
  const { data: slotsDisponiveis = [], isFetching: loadingSlots } = useQuery<string[]>({
    queryKey: ["disponibilidade", form.medico_id, form.data],
    queryFn: () => medicosService.disponibilidade(form.medico_id, form.data),
    enabled: !!form.medico_id && !!form.data,
    staleTime: 2 * 60_000,
  })

  // ── Grouped consultas ─────────────────────────────────────────────────────

  const consultasPorDia = useMemo(() => {
    const map = new Map<string, Consulta[]>()
    for (const c of consultas) {
      const key = format(parseISO(c.data_hora), "yyyy-MM-dd")
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(c)
    }
    return map
  }, [consultas])

  const consultasDia = useMemo(
    () => (consultasPorDia.get(format(diaSelected, "yyyy-MM-dd")) ?? [])
      .sort((a, b) => a.data_hora.localeCompare(b.data_hora)),
    [consultasPorDia, diaSelected],
  )

  // ── Mutations ─────────────────────────────────────────────────────────────

  const atualizarStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ConsultaStatus }) =>
      consultasService.atualizar(id, { status }),
    onSuccess: (updated) => {
      setConsultaOpen(updated)
      qc.invalidateQueries({ queryKey: ["consultas-semana"] })
    },
  })

  const criarConsulta = useMutation({
    mutationFn: (data: CriarConsultaDTO) => consultasService.criar(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["consultas-semana"] })
      closeModal()
    },
  })

  // ── Modal helpers ─────────────────────────────────────────────────────────

  function openModal(diaPreenchido?: Date) {
    setForm({
      ...FORM_EMPTY,
      data: format(diaPreenchido ?? diaSelected, "yyyy-MM-dd"),
    })
    setFormErrors({})
    setModal(true)
  }

  function closeModal() {
    setModal(false)
    setFormErrors({})
  }

  function handleField<K extends keyof CreateForm>(key: K, value: CreateForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    if (formErrors[key]) setFormErrors((e) => ({ ...e, [key]: undefined }))
  }

  function validate(): boolean {
    const e: Partial<Record<keyof CreateForm, string>> = {}
    if (!form.paciente_id) e.paciente_id = "Seleccione um paciente"
    if (!form.medico_id)   e.medico_id   = "Seleccione um médico"
    if (!form.data)        e.data        = "Obrigatório"
    if (!form.hora)        e.hora        = "Obrigatório"
    setFormErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    const [h, m] = form.hora.split(":").map(Number)
    const dt = setMinutes(setHours(parseISO(form.data), h), m)

    criarConsulta.mutate({
      paciente_id: form.paciente_id as string,
      medico_id:   form.medico_id   as string,
      data_hora:   dt.toISOString(),
      tipo:        form.tipo,
      duracao_min: form.duracao_min,
      valor:       form.valor ? parseFloat(form.valor) : undefined,
      observacoes: form.observacoes || undefined,
      // status e pago são adicionados internamente por consultasService.criar()
    })
  }

  const isSaving   = criarConsulta.isPending
  const saveError  = criarConsulta.error as Error | null

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full gap-4">

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setSemana((d) => subWeeks(d, 1))}
            className="p-1.5 rounded-lg hover:bg-surface-100 transition-colors"
          >
            <ChevronLeft size={16} className="text-surface-500" />
          </button>
          <span className="text-sm text-surface-600 w-44 text-center font-medium">
            {format(inicioSemana, "d MMM", { locale: dateFnsLocale })}
            {" — "}
            {format(fimSemana, "d MMM yyyy", { locale: dateFnsLocale })}
          </span>
          <button
            onClick={() => setSemana((d) => addWeeks(d, 1))}
            className="p-1.5 rounded-lg hover:bg-surface-100 transition-colors"
          >
            <ChevronRight size={16} className="text-surface-500" />
          </button>
        </div>

        <button
          onClick={() => { setSemana(new Date()); setDiaSelected(new Date()) }}
          className="text-xs text-brand-600 px-3 py-1.5 rounded-lg border border-brand-200 hover:bg-brand-50 transition-colors"
        >
          Hoje
        </button>

        <div className="ml-auto">
          <button
            onClick={() => openModal()}
            className="flex items-center gap-1.5 bg-brand-600 text-white text-sm font-medium
                       px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors"
          >
            <Plus size={14} />
            Nova consulta
          </button>
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div className="flex gap-4 flex-1 min-h-0">

        {/* ── Weekly calendar ────────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0">
          {loadingConsultas ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 size={24} className="animate-spin text-brand-500" />
            </div>
          ) : (
            <div className="grid grid-cols-6 gap-2 flex-1 min-h-0">
              {diasSemana.map((dia) => {
                const key   = format(dia, "yyyy-MM-dd")
                const isHoje = isSameDay(dia, new Date())
                const isSel  = isSameDay(dia, diaSelected)
                const lista  = (consultasPorDia.get(key) ?? [])
                  .sort((a, b) => a.data_hora.localeCompare(b.data_hora))

                return (
                  <div key={key} className="flex flex-col">
                    {/* Day header */}
                    <button
                      onClick={() => setDiaSelected(dia)}
                      className={`text-center py-2 mb-2 rounded-xl transition-colors ${
                        isHoje
                          ? "bg-brand-600"
                          : isSel
                          ? "bg-brand-50 border border-brand-200"
                          : "hover:bg-surface-100"
                      }`}
                    >
                      <p className={`text-xs capitalize ${isHoje ? "text-blue-200" : "text-surface-400"}`}>
                        {format(dia, "EEE", { locale: dateFnsLocale })}
                      </p>
                      <p className={`text-sm font-bold ${isHoje ? "text-white" : isSel ? "text-brand-700" : "text-surface-700"}`}>
                        {format(dia, "d")}
                      </p>
                      {lista.length > 0 && (
                        <p className={`text-xs mt-0.5 ${isHoje ? "text-blue-200" : "text-surface-400"}`}>
                          {lista.length} consulta{lista.length > 1 ? "s" : ""}
                        </p>
                      )}
                    </button>

                    {/* Event pills */}
                    <div className="space-y-1.5 overflow-y-auto flex-1">
                      {lista.map((c) => (
                        <ConsultaCard
                          key={c.id}
                          consulta={c}
                          onClick={() => { setDiaSelected(dia); setConsultaOpen(c) }}
                        />
                      ))}
                      {lista.length === 0 && (
                        <button
                          onClick={() => openModal(dia)}
                          className="w-full border-2 border-dashed border-surface-100 rounded-lg py-4
                                     text-surface-300 text-xs hover:border-brand-200 hover:text-brand-400
                                     transition-colors"
                        >
                          +
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Day panel ──────────────────────────────────────────────────── */}
        <div className="w-72 shrink-0 flex flex-col gap-3">

          {/* Day title */}
          <div className="bg-white rounded-xl border border-surface-100 shadow-sm px-4 py-3 flex items-center justify-between">
            <div>
              <p className="text-xs text-surface-400 capitalize">
                {format(diaSelected, "EEEE", { locale: dateFnsLocale })}
              </p>
              <p className="text-sm font-semibold text-surface-800">
                {format(diaSelected, "d 'de' MMMM", { locale: dateFnsLocale })}
              </p>
            </div>
            <button
              onClick={() => openModal(diaSelected)}
              className="p-1.5 rounded-lg bg-brand-50 text-brand-600 hover:bg-brand-100 transition-colors"
            >
              <Plus size={14} />
            </button>
          </div>

          {/* Consulta detail — when one is selected */}
          {consultaOpen && isSameDay(parseISO(consultaOpen.data_hora), diaSelected) && (
            <ConsultaDetalhe
              consulta={consultaOpen}
              onClose={() => setConsultaOpen(null)}
              onStatusChange={(status) => atualizarStatus.mutate({ id: consultaOpen.id, status })}
              isPending={atualizarStatus.isPending}
            />
          )}

          {/* Time slots list */}
          <div className="bg-white rounded-xl border border-surface-100 shadow-sm flex-1 overflow-y-auto">
            <div className="divide-y divide-surface-50">
              {HORAS_DIA.map((hora) => {
                const consulta = consultasDia.find(
                  (c) => format(parseISO(c.data_hora), "HH:mm") === hora,
                )
                return (
                  <div key={hora} className="flex items-start gap-2 px-3 py-2 min-h-[2.5rem]">
                    <span className="text-xs font-mono text-surface-300 w-10 shrink-0 pt-0.5">
                      {hora}
                    </span>
                    {consulta ? (
                      <button
                        onClick={() => setConsultaOpen(consulta)}
                        className={`flex-1 text-left border-l-2 rounded-r-lg px-2 py-1 transition-colors hover:opacity-80 ${STATUS_PILL[consulta.status]}`}
                      >
                        <p className="text-xs font-medium truncate">
                          {consulta.pacientes?.nome ?? "—"}
                        </p>
                        <p className="text-xs opacity-70 truncate">
                          {consulta.medicos?.nome ?? "—"}
                        </p>
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setForm((f) => ({ ...f, data: format(diaSelected, "yyyy-MM-dd"), hora }))
                          setModal(true)
                          setFormErrors({})
                        }}
                        className="flex-1 h-full rounded-lg hover:bg-surface-50 transition-colors"
                      />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── Create modal ─────────────────────────────────────────────────── */}
      {modal && (
        <Modal title="Nova consulta" onClose={closeModal}>
          <div className="space-y-4">
            {saveError && (
              <ErrorBanner message={saveError.message} />
            )}

            {/* Paciente */}
            <PacienteSearch
              pacientes={pacientes}
              value={form.paciente_nome}
              selectedId={form.paciente_id}
              error={formErrors.paciente_id}
              onSelect={(p) => {
                handleField("paciente_id",   p.id)
                handleField("paciente_nome", p.nome)
              }}
            />

            {/* Médico */}
            <Field label="Médico *" error={formErrors.medico_id}>
              <select
                value={form.medico_id}
                onChange={(e) => {
                  handleField("medico_id", e.target.value)
                  handleField("hora", "")
                }}
                className={inputCls(!!formErrors.medico_id)}
              >
                <option value="">Seleccionar médico…</option>
                {medicos.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.nome} — {m.especialidade}
                  </option>
                ))}
              </select>
            </Field>

            {/* Data + Hora (row) */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Data *" error={formErrors.data}>
                <input
                  type="date"
                  value={form.data}
                  onChange={(e) => {
                    handleField("data", e.target.value)
                    handleField("hora", "")
                  }}
                  className={inputCls(!!formErrors.data)}
                />
              </Field>

              <Field label="Hora *" error={formErrors.hora}>
                {form.medico_id && slotsDisponiveis.length > 0 ? (
                  <div className="relative">
                    <select
                      value={form.hora}
                      onChange={(e) => handleField("hora", e.target.value)}
                      className={inputCls(!!formErrors.hora)}
                    >
                      <option value="">Seleccionar…</option>
                      {slotsDisponiveis.map((slot) => (
                        <option key={slot} value={slot}>{slot}</option>
                      ))}
                    </select>
                    {loadingSlots && (
                      <Loader2 size={12} className="absolute right-8 top-3 animate-spin text-surface-400" />
                    )}
                  </div>
                ) : (
                  <input
                    type="time"
                    value={form.hora}
                    onChange={(e) => handleField("hora", e.target.value)}
                    step={1800}
                    className={inputCls(!!formErrors.hora)}
                  />
                )}
              </Field>
            </div>

            {/* Availability notice */}
            {form.medico_id && form.data && slotsDisponiveis.length === 0 && !loadingSlots && (
              <p className="text-xs text-orange-600 flex items-center gap-1.5">
                <AlertTriangle size={12} />
                Sem horários configurados para este médico. Use o input manual.
              </p>
            )}

            {/* Tipo + Duração (row) */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Tipo">
                <select
                  value={form.tipo}
                  onChange={(e) => handleField("tipo", e.target.value as ConsultaTipo)}
                  className={inputCls(false)}
                >
                  {(Object.entries(TIPO_LABEL) as [ConsultaTipo, string][]).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </Field>

              <Field label="Duração (min)">
                <input
                  type="number"
                  min={15}
                  max={240}
                  step={15}
                  value={form.duracao_min}
                  onChange={(e) => handleField("duracao_min", parseInt(e.target.value) || 30)}
                  className={inputCls(false)}
                />
              </Field>
            </div>

            {/* Valor */}
            <Field label="Valor (€)">
              <input
                type="number"
                min={0}
                step={0.01}
                placeholder="0.00"
                value={form.valor}
                onChange={(e) => handleField("valor", e.target.value)}
                className={inputCls(false)}
              />
            </Field>

            {/* Observações */}
            <Field label="Observações">
              <textarea
                value={form.observacoes}
                onChange={(e) => handleField("observacoes", e.target.value)}
                rows={2}
                placeholder="Notas adicionais…"
                className={`${inputCls(false)} resize-none`}
              />
            </Field>
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
              Agendar consulta
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ConsultaCard({ consulta, onClick }: { consulta: Consulta; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left border-l-2 rounded-r-lg px-2.5 py-2 transition-all hover:opacity-80 ${STATUS_PILL[consulta.status]}`}
    >
      <p className="text-xs font-mono opacity-60 mb-0.5">
        {format(parseISO(consulta.data_hora), "HH:mm")}
      </p>
      <p className="text-xs font-medium leading-tight truncate">
        {consulta.pacientes?.nome ?? "—"}
      </p>
      <p className="text-xs opacity-60 truncate">
        {consulta.medicos?.nome ?? "—"}
      </p>
    </button>
  )
}

function ConsultaDetalhe({
  consulta,
  onClose,
  onStatusChange,
  isPending,
}: {
  consulta: Consulta
  onClose: () => void
  onStatusChange: (s: ConsultaStatus) => void
  isPending: boolean
}) {
  const STATUS_ACTIONS: ConsultaStatus[] = ["agendada", "confirmada", "realizada", "cancelada", "falta"]

  return (
    <div className="bg-white rounded-xl border border-surface-100 shadow-sm p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[consulta.status]}`}>
            {STATUS_LABEL[consulta.status]}
          </span>
          <span className="text-xs text-surface-400">
            {format(parseISO(consulta.data_hora), "HH:mm")}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded text-surface-400 hover:text-surface-700 hover:bg-surface-50"
        >
          <X size={13} />
        </button>
      </div>

      <div className="space-y-2 text-sm mb-3">
        <div className="flex items-center gap-2 text-surface-700">
          <User size={13} className="text-surface-400 shrink-0" />
          <span className="truncate">{consulta.pacientes?.nome ?? "—"}</span>
        </div>
        <div className="flex items-center gap-2 text-surface-700">
          <Stethoscope size={13} className="text-surface-400 shrink-0" />
          <span className="truncate">{consulta.medicos?.nome ?? "—"}</span>
        </div>
        <div className="flex items-center gap-2 text-surface-700">
          <Clock size={13} className="text-surface-400 shrink-0" />
          <span>{consulta.duracao_min} min · {TIPO_LABEL[consulta.tipo]}</span>
        </div>
        {consulta.valor != null && (
          <div className="flex items-center gap-2 text-surface-700">
            <span className="text-surface-400 text-xs w-[13px] text-center shrink-0">€</span>
            <span>{consulta.valor.toFixed(2)}</span>
            {consulta.pago && (
              <span className="text-xs text-emerald-600 font-medium">· Pago</span>
            )}
          </div>
        )}
      </div>

      {/* Status actions */}
      <div className="border-t border-surface-50 pt-3">
        <p className="text-xs text-surface-400 mb-2">Actualizar status</p>
        <div className="flex flex-wrap gap-1.5">
          {STATUS_ACTIONS.map((s) => (
            <button
              key={s}
              disabled={consulta.status === s || isPending}
              onClick={() => onStatusChange(s)}
              className={`text-xs px-2.5 py-1 rounded-lg border capitalize transition-colors ${
                consulta.status === s
                  ? `${STATUS_BADGE[s]} border-transparent font-medium`
                  : "border-surface-200 text-surface-500 hover:border-surface-300 hover:bg-surface-50"
              } disabled:cursor-not-allowed`}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Patient autocomplete ─────────────────────────────────────────────────────

function PacienteSearch({
  pacientes,
  value,
  selectedId,
  error,
  onSelect,
}: {
  pacientes: Paciente[]
  value: string
  selectedId: string
  error?: string
  onSelect: (p: Paciente) => void
}) {
  const [query,   setQuery]   = useState(value)
  const [open,    setOpen]    = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => { setQuery(value) }, [value])

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const filtered = useMemo(
    () =>
      query.length < 1
        ? pacientes.slice(0, 8)
        : pacientes
            .filter(
              (p) =>
                p.nome.toLowerCase().includes(query.toLowerCase()) ||
                p.telefone.includes(query),
            )
            .slice(0, 8),
    [pacientes, query],
  )

  return (
    <Field label="Paciente *" error={error}>
      <div ref={ref} className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder="Pesquisar paciente…"
          className={inputCls(!!error)}
          autoComplete="off"
        />

        {selectedId && !open && (
          <CheckCircle size={14} className="absolute right-3 top-3 text-emerald-500" />
        )}

        {open && filtered.length > 0 && (
          <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-surface-200
                          rounded-xl shadow-lg overflow-hidden">
            {filtered.map((p) => (
              <button
                key={p.id}
                onMouseDown={(e) => { e.preventDefault(); onSelect(p); setOpen(false) }}
                className="w-full text-left px-3.5 py-2.5 hover:bg-surface-50 transition-colors flex items-center justify-between gap-2"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-surface-800 truncate">{p.nome}</p>
                  <p className="text-xs text-surface-400 font-mono">{p.telefone}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${
                  p.status === "ativo" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
                }`}>
                  {p.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </Field>
  )
}

// ─── Generic helpers ──────────────────────────────────────────────────────────

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
      {label && <label className="block text-xs font-medium text-surface-700">{label}</label>}
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

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
      <AlertCircle size={15} className="mt-0.5 shrink-0" />
      {message}
    </div>
  )
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
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[92vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-100 sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <Calendar size={16} className="text-brand-600" />
            <h2 className="text-base font-semibold text-surface-800">{title}</h2>
          </div>
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
