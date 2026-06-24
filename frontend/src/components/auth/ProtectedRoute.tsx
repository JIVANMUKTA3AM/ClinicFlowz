import { Navigate, Outlet } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { useAuthStore } from "../../store/authStore"

function Spinner() {
  return (
    <div className="flex h-screen items-center justify-center bg-surface-50">
      <Loader2 size={28} className="animate-spin text-brand-600" />
    </div>
  )
}

/** Protects routes that require auth + clinica configurada. */
export function ProtectedRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading       = useAuthStore((s) => s.isLoading)
  const user            = useAuthStore((s) => s.user)

  if (isLoading)       return <Spinner />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (!user?.clinica_id) return <Navigate to="/onboarding" replace />

  return <Outlet />
}

/** Protects the /onboarding route: auth required, sem clinica_id. */
export function OnboardingRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading       = useAuthStore((s) => s.isLoading)
  const user            = useAuthStore((s) => s.user)

  if (isLoading)          return <Spinner />
  if (!isAuthenticated)   return <Navigate to="/login" replace />
  if (user?.clinica_id)   return <Navigate to="/dashboard" replace />

  return <Outlet />
}
