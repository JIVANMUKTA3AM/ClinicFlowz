import { useEffect } from "react"
import { useAuthStore } from "../store/authStore"

/**
 * Initialises the Supabase session on first mount and exposes
 * the auth state + actions from the Zustand store.
 *
 * Use this hook once at the top of the component tree (App.tsx).
 * Every other component can call useAuthStore() directly.
 */
export function useAuth() {
  const { initialize, ...auth } = useAuthStore()

  useEffect(() => {
    initialize()
  }, [initialize])

  return auth
}

// Re-export store selector shortcuts so consumers don't need two imports
export { useAuthStore }
