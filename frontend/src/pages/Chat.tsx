import {
  useState, useEffect, useRef, useMemo, useCallback,
} from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { format, isToday, isYesterday, parseISO } from "date-fns"
import { ptBR, pt } from "date-fns/locale"
import {
  Search, Send, Phone, CheckCheck, AlertCircle, Loader2,
  MessageSquare, Calendar, FileText, Bell, Info, User,
  Wifi, WifiOff, MoreVertical,
  type LucideIcon,
} from "lucide-react"
import { pacientesService, timelineService } from "../services/api"
import { useAuthStore } from "../store/authStore"
import type { Paciente, Interacao, InteracaoTipo } from "../types"

// ─── Constants ────────────────────────────────────────────────────────────────

const POLL_INTERVAL = 5_000 // 5 s

// Which tipos render as chat bubbles vs info cards
const BUBBLE_TIPOS: InteracaoTipo[] = ["whatsapp", "sms"]

const TIPO_ICON: Record<InteracaoTipo, LucideIcon> = {
  whatsapp: MessageSquare,
  sms:      MessageSquare,
  email:    Info,
  ligacao:  Phone,
  nota:     FileText,
  lembrete: Bell,
  consulta: Calendar,
}

const TIPO_LABEL: Record<InteracaoTipo, string> = {
  whatsapp: "WhatsApp",
  sms:      "SMS",
  email:    "Email",
  ligacao:  "Ligação",
  nota:     "Nota",
  lembrete: "Lembrete",
  consulta: "Consulta",
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function msgTime(iso: string): string {
  const d = parseISO(iso)
  if (isToday(d))     return format(d, "HH:mm")
  if (isYesterday(d)) return "Ontem"
  return format(d, "dd/MM/yyyy", { locale: ptBR })
}

function fullTime(iso: string): string {
  return format(parseISO(iso), "dd/MM/yyyy HH:mm", { locale: ptBR })
}

function initials(nome: string) {
  return nome.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function Chat() {
  const qc   = useQueryClient()
  const pais = useAuthStore((s) => s.user?.pais ?? "PT")
  const dateFnsLocale = pais === "PT" ? pt : ptBR

  const [search,       setSearch]      = useState("")
  const [selected,     setSelected]    = useState<Paciente | null>(null)
  const [text,         setText]        = useState("")
  const [isOnline,     setIsOnline]    = useState(true)
  const endRef   = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // ── Queries ───────────────────────────────────────────────────────────────

  const { data: pacientes = [] } = useQuery<Paciente[]>({
    queryKey: ["pacientes", search],
    queryFn: () => pacientesService.listar(search ? { q: search } : {}),
    staleTime: 30_000,
  })

  // Timeline with polling
  const {
    data: rawTimeline = [],
    isFetching,
    isError,
  } = useQuery<Interacao[]>({
    queryKey: ["timeline", selected?.id],
    queryFn: () => timelineService.paciente(selected!.id),
    enabled: !!selected,
    refetchInterval: POLL_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: 0,
  })

  // Timeline sorted oldest→newest for display (API returns desc)
  const timeline = useMemo(
    () => [...rawTimeline].reverse(),
    [rawTimeline],
  )

  // Last interaction per patient (for conversation list preview)
  const lastMsg = useMemo<Map<string, Interacao>>(() => {
    if (!selected || !rawTimeline.length) return new Map()
    return new Map([[selected.id, rawTimeline[0]]])
  }, [selected, rawTimeline])

  // ── Mutation ──────────────────────────────────────────────────────────────

  const sendMsg = useMutation({
    mutationFn: (conteudo: string) =>
      timelineService.criar({
        paciente_id: selected!.id,
        tipo: "whatsapp",
        direcao: "saida",
        conteudo,
        criado_por: "recepcao",
      }),
    onSuccess: () => {
      setText("")
      qc.invalidateQueries({ queryKey: ["timeline", selected?.id] })
    },
  })

  // ── Online detection ──────────────────────────────────────────────────────

  useEffect(() => {
    const on  = () => setIsOnline(true)
    const off = () => setIsOnline(false)
    window.addEventListener("online",  on)
    window.addEventListener("offline", off)
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off) }
  }, [])

  // ── Scroll to bottom on new messages ─────────────────────────────────────

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [timeline.length])

  // ── Send helpers ──────────────────────────────────────────────────────────

  function handleSend() {
    const trimmed = text.trim()
    if (!trimmed || sendMsg.isPending || !selected) return
    sendMsg.mutate(trimmed)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full bg-white rounded-2xl border border-surface-100 shadow-sm overflow-hidden">

      {/* ── Left: conversation list ───────────────────────────────────────── */}
      <aside className="w-80 shrink-0 flex flex-col border-r border-surface-100">

        {/* Header */}
        <div className="px-4 pt-4 pb-3 border-b border-surface-100">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-surface-800">Conversas</h2>
            <div className={`flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full ${
              isOnline ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"
            }`}>
              {isOnline
                ? <><Wifi size={11} /> Online</>
                : <><WifiOff size={11} /> Offline</>
              }
            </div>
          </div>

          {/* Search */}
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Pesquisar paciente…"
              className="w-full pl-8 pr-3 py-2 text-sm bg-surface-100 rounded-xl border-none
                         focus:outline-none focus:ring-2 focus:ring-brand-500/20 transition placeholder-surface-400"
            />
          </div>
        </div>

        {/* Patient list */}
        <div className="flex-1 overflow-y-auto">
          {pacientes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-surface-400 gap-2">
              <User size={24} className="opacity-40" />
              <p className="text-xs">Nenhum paciente</p>
            </div>
          ) : (
            pacientes.map((p) => {
              const last = lastMsg.get(p.id)
              const isActive = selected?.id === p.id
              return (
                <button
                  key={p.id}
                  onClick={() => setSelected(p)}
                  className={`w-full text-left flex items-center gap-3 px-4 py-3 transition-colors
                    border-b border-surface-50
                    ${isActive ? "bg-brand-50" : "hover:bg-surface-50"}`}
                >
                  {/* Avatar */}
                  <div className={`w-10 h-10 rounded-full shrink-0 flex items-center justify-center
                                   text-sm font-bold
                                   ${isActive ? "bg-brand-600 text-white" : "bg-surface-200 text-surface-600"}`}>
                    {initials(p.nome)}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-1">
                      <p className={`text-sm font-semibold truncate leading-tight
                        ${isActive ? "text-brand-700" : "text-surface-800"}`}>
                        {p.nome}
                      </p>
                      {last && (
                        <span className="text-[10px] text-surface-400 shrink-0 mt-0.5">
                          {msgTime(last.created_at)}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-surface-400 truncate mt-0.5 font-mono">{p.telefone}</p>
                    {last && (
                      <p className="text-xs text-surface-400 truncate mt-0.5 leading-snug">
                        {last.direcao === "saida" && (
                          <CheckCheck size={10} className="inline mr-1 text-brand-400" />
                        )}
                        {last.conteudo}
                      </p>
                    )}
                  </div>
                </button>
              )
            })
          )}
        </div>
      </aside>

      {/* ── Right: chat view ─────────────────────────────────────────────── */}
      {selected ? (
        <div className="flex-1 flex flex-col min-w-0">

          {/* Chat header */}
          <div className="flex items-center gap-3 px-5 py-3 border-b border-surface-100 bg-surface-50 shrink-0">
            <div className="w-9 h-9 rounded-full bg-brand-600 flex items-center justify-center text-white text-sm font-bold shrink-0">
              {initials(selected.nome)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-surface-800 truncate">{selected.nome}</p>
              <div className="flex items-center gap-2">
                <p className="text-xs text-surface-400 font-mono">{selected.telefone}</p>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium capitalize ${
                  selected.status === "ativo"   ? "bg-emerald-100 text-emerald-700" :
                  selected.status === "lead"    ? "bg-slate-100 text-slate-600"    :
                  selected.status === "inativo" ? "bg-orange-100 text-orange-700"  :
                  "bg-red-100 text-red-600"
                }`}>
                  {selected.status}
                </span>
                {isFetching && (
                  <Loader2 size={10} className="animate-spin text-surface-300" />
                )}
              </div>
            </div>
            <button className="p-2 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-100 transition">
              <MoreVertical size={16} />
            </button>
          </div>

          {/* Messages area */}
          <div
            className="flex-1 overflow-y-auto px-5 py-4 space-y-1"
            style={{ background: "url(\"data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23e2e8f0' fill-opacity='0.3'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E\")" }}
          >
            {isError && (
              <div className="flex items-center gap-2 justify-center py-3 text-xs text-red-500">
                <AlertCircle size={13} />
                Erro ao carregar mensagens.
              </div>
            )}

            {timeline.length === 0 && !isFetching && (
              <div className="flex flex-col items-center justify-center h-full text-surface-400 gap-2 pt-12">
                <MessageSquare size={32} className="opacity-30" />
                <p className="text-sm">Sem mensagens ainda.</p>
                <p className="text-xs">Envie a primeira mensagem abaixo.</p>
              </div>
            )}

            {/* Day separators + messages */}
            <MessageList timeline={timeline} dateFnsLocale={dateFnsLocale} />

            {/* Scroll anchor */}
            <div ref={endRef} />
          </div>

          {/* Send area */}
          <div className="shrink-0 border-t border-surface-100 bg-surface-50 px-4 py-3">
            {sendMsg.isError && (
              <p className="text-xs text-red-500 mb-2 flex items-center gap-1.5">
                <AlertCircle size={11} />
                {(sendMsg.error as Error).message}
              </p>
            )}
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Escreva uma mensagem… (Enter para enviar)"
                rows={1}
                className="flex-1 resize-none rounded-2xl border border-surface-200 bg-white
                           px-4 py-2.5 text-sm text-surface-800 placeholder-surface-400
                           focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400
                           transition max-h-28 overflow-y-auto leading-relaxed"
                style={{ minHeight: "42px" }}
                onInput={(e) => {
                  const el = e.currentTarget
                  el.style.height = "auto"
                  el.style.height = Math.min(el.scrollHeight, 112) + "px"
                }}
              />
              <button
                onClick={handleSend}
                disabled={!text.trim() || sendMsg.isPending}
                className="w-10 h-10 rounded-full bg-brand-600 text-white flex items-center justify-center
                           hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed
                           transition-all shrink-0 shadow-sm"
              >
                {sendMsg.isPending
                  ? <Loader2 size={16} className="animate-spin" />
                  : <Send size={16} />
                }
              </button>
            </div>
            <p className="text-[10px] text-surface-400 mt-1.5 text-center">
              Shift+Enter para nova linha · mensagem gravada na timeline do paciente
            </p>
          </div>
        </div>
      ) : (
        <EmptyState />
      )}
    </div>
  )
}

// ─── Message list with day separators ────────────────────────────────────────

function MessageList({ timeline, dateFnsLocale = ptBR }: { timeline: Interacao[]; dateFnsLocale?: typeof ptBR }) {
  if (timeline.length === 0) return null

  const groups: { day: string; items: Interacao[] }[] = []
  let currentDay = ""

  for (const item of timeline) {
    const day = format(parseISO(item.created_at), "yyyy-MM-dd")
    if (day !== currentDay) {
      currentDay = day
      groups.push({ day, items: [] })
    }
    groups[groups.length - 1].items.push(item)
  }

  return (
    <>
      {groups.map(({ day, items }) => (
        <div key={day}>
          {/* Day label */}
          <DaySeparator dateStr={day} dateFnsLocale={dateFnsLocale} />

          {/* Messages */}
          <div className="space-y-1 mt-2">
            {items.map((item, idx) => {
              const prevItem = idx > 0 ? items[idx - 1] : null
              const sameDir = prevItem?.direcao === item.direcao

              if (BUBBLE_TIPOS.includes(item.tipo)) {
                return (
                  <Bubble
                    key={item.id}
                    item={item}
                    compact={sameDir}
                  />
                )
              }
              return <InfoCard key={item.id} item={item} />
            })}
          </div>
        </div>
      ))}
    </>
  )
}

// ─── Day separator ────────────────────────────────────────────────────────────

function DaySeparator({ dateStr, dateFnsLocale = ptBR }: { dateStr: string; dateFnsLocale?: typeof ptBR }) {
  const d = parseISO(dateStr)
  let label: string
  if (isToday(d))     label = "Hoje"
  else if (isYesterday(d)) label = "Ontem"
  else label = format(d, "d 'de' MMMM 'de' yyyy", { locale: dateFnsLocale })

  return (
    <div className="flex items-center gap-3 my-3">
      <div className="flex-1 h-px bg-surface-200" />
      <span className="text-[11px] text-surface-400 bg-surface-100 px-3 py-1 rounded-full font-medium shrink-0">
        {label}
      </span>
      <div className="flex-1 h-px bg-surface-200" />
    </div>
  )
}

// ─── Chat bubble (WhatsApp / SMS) ─────────────────────────────────────────────

function Bubble({ item, compact }: { item: Interacao; compact: boolean }) {
  const isSent = item.direcao === "saida"

  return (
    <div className={`flex ${isSent ? "justify-end" : "justify-start"} ${compact ? "mt-0.5" : "mt-2"}`}>
      <div
        className={`max-w-[72%] group relative px-3.5 py-2 rounded-2xl shadow-sm
          ${isSent
            ? "bg-brand-600 text-white rounded-br-sm"
            : "bg-white text-surface-800 rounded-bl-sm border border-surface-100"
          }`}
      >
        {/* Agent label (only on outbound AI messages) */}
        {isSent && item.criado_por !== "recepcao" && (
          <p className={`text-[10px] font-medium mb-0.5 ${isSent ? "text-brand-200" : "text-brand-500"}`}>
            {item.criado_por}
          </p>
        )}

        {/* Message text */}
        <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{item.conteudo}</p>

        {/* Timestamp + tick */}
        <div className={`flex items-center justify-end gap-1 mt-1 ${isSent ? "text-brand-200" : "text-surface-300"}`}>
          <span className="text-[10px]">
            {format(parseISO(item.created_at), "HH:mm")}
          </span>
          {isSent && <CheckCheck size={11} />}
        </div>
      </div>
    </div>
  )
}

// ─── Info card (nota, consulta, lembrete, ligacao, email) ────────────────────

function InfoCard({ item }: { item: Interacao }) {
  const Icon = TIPO_ICON[item.tipo] ?? Info

  const colors: Record<string, string> = {
    nota:     "bg-amber-50 border-amber-200 text-amber-700",
    consulta: "bg-blue-50 border-blue-200 text-blue-700",
    lembrete: "bg-purple-50 border-purple-200 text-purple-700",
    ligacao:  "bg-slate-50 border-slate-200 text-slate-600",
    email:    "bg-indigo-50 border-indigo-200 text-indigo-700",
  }

  const cls = colors[item.tipo] ?? "bg-surface-50 border-surface-200 text-surface-600"

  return (
    <div className="flex justify-center my-2">
      <div className={`flex items-start gap-2 rounded-xl border px-3.5 py-2.5 max-w-[80%] shadow-sm ${cls}`}>
        <Icon size={13} className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider opacity-70">
              {TIPO_LABEL[item.tipo]}
            </span>
            <span className="text-[10px] opacity-60">{fullTime(item.created_at)}</span>
          </div>
          <p className="text-xs leading-snug whitespace-pre-wrap break-words">{item.conteudo}</p>
          <p className="text-[10px] opacity-50 mt-0.5">por {item.criado_por}</p>
        </div>
      </div>
    </div>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-surface-400 gap-4 bg-surface-50">
      <div className="w-20 h-20 rounded-full bg-surface-100 flex items-center justify-center">
        <MessageSquare size={32} className="text-surface-300" />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-surface-600">Seleccione uma conversa</p>
        <p className="text-xs text-surface-400 mt-1">
          Escolha um paciente à esquerda para ver o histórico
        </p>
      </div>
    </div>
  )
}
