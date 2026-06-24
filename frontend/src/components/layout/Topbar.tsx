import { Bell, ChevronDown } from "lucide-react"
import { useAuthStore } from "../../store/authStore"

interface TopbarProps {
  title?: string
}

export function Topbar({ title }: TopbarProps) {
  const user = useAuthStore((s) => s.user)

  const initials = user?.nome
    ? user.nome.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()
    : user?.email?.[0]?.toUpperCase() ?? "?"

  return (
    <header className="h-14 border-b border-surface-100 bg-white flex items-center justify-between px-6 shrink-0">
      {/* Left — page title */}
      <h2 className="text-sm font-semibold text-surface-800 tracking-tight">
        {title ?? ""}
      </h2>

      {/* Right — notifications + user badge */}
      <div className="flex items-center gap-3">
        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-surface-400 hover:text-surface-700 hover:bg-surface-50 transition">
          <Bell size={17} />
        </button>

        {/* User badge */}
        <button className="flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-lg hover:bg-surface-50 transition group">
          {/* Avatar */}
          <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
            {initials}
          </div>

          <div className="text-left hidden sm:block">
            <p className="text-xs font-medium text-surface-800 leading-none">
              {user?.nome ?? user?.email ?? "—"}
            </p>
            {user?.nome && (
              <p className="text-[10px] text-surface-400 mt-0.5 leading-none truncate max-w-[140px]">
                {user.email}
              </p>
            )}
          </div>

          <ChevronDown size={13} className="text-surface-400 group-hover:text-surface-600 transition" />
        </button>
      </div>
    </header>
  )
}
