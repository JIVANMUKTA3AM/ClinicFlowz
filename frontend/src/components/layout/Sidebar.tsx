import { NavLink, useNavigate } from "react-router-dom"
import {
  LayoutDashboard, Users, CalendarDays, GitMerge,
  MessageSquare, Stethoscope, LogOut, ChevronRight, DoorOpen,
  BarChart3, Settings,
} from "lucide-react"
import { useAuthStore } from "../../store/authStore"

const NAV = [
  { to: "/dashboard",  icon: LayoutDashboard, label: "Dashboard" },
  { to: "/pacientes",  icon: Users,           label: "Pacientes" },
  { to: "/agenda",     icon: CalendarDays,    label: "Agenda" },
  { to: "/pipeline",   icon: GitMerge,        label: "Pipeline" },
  { to: "/whatsapp",   icon: MessageSquare,   label: "WhatsApp" },
  { to: "/medicos",    icon: Stethoscope,     label: "Médicos" },
  { to: "/salas",      icon: DoorOpen,        label: "Salas" },
  { to: "/financeiro",    icon: BarChart3, label: "Financeiro" },
  { to: "/configuracoes", icon: Settings,  label: "Configurações" },
]

export function Sidebar() {
  const navigate = useNavigate()
  const logout   = useAuthStore((s) => s.logout)

  async function handleLogout() {
    await logout()
    navigate("/login", { replace: true })
  }

  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-surface-900 flex flex-col z-30">
      {/* Logo */}
      <div className="px-5 py-6 border-b border-surface-800">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center">
            <Stethoscope size={14} className="text-white" />
          </div>
          <span className="text-white font-semibold text-sm tracking-tight">ClinicFlow</span>
        </div>
        <p className="text-surface-700 text-xs mt-1 font-mono">v1.0</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all group ${
                isActive
                  ? "bg-brand-600 text-white font-medium"
                  : "text-slate-400 hover:text-white hover:bg-surface-800"
              }`
            }
          >
            <Icon size={16} />
            <span className="flex-1">{label}</span>
            <ChevronRight size={12} className="opacity-0 group-hover:opacity-40 transition-opacity" />
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-3 pb-5">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-surface-800 transition-all"
        >
          <LogOut size={16} />
          <span>Terminar sessão</span>
        </button>
      </div>
    </aside>
  )
}
