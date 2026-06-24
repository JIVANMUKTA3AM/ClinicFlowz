import { create } from "zustand"
import { supabase } from "../lib/supabase"
import type { User, Pais } from "../types"

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean

  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  initialize: () => Promise<void>
}

function buildUser(supabaseUser: { id: string; email?: string }, meta: Record<string, unknown>): User {
  return {
    id: supabaseUser.id,
    email: supabaseUser.email!,
    clinica_id: (meta.clinica_id as string) ?? "",
    nome: meta.nome as string | undefined,
    pais: ((meta.pais as string) ?? "PT").toUpperCase() as Pais,
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,

  login: async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw new Error(error.message)

    const session = data.session!
    const meta = data.user?.user_metadata ?? {}

    set({
      token: session.access_token,
      isAuthenticated: true,
      user: buildUser(data.user!, meta),
    })
  },

  logout: async () => {
    await supabase.auth.signOut()
    set({ user: null, token: null, isAuthenticated: false })
  },

  initialize: async () => {
    set({ isLoading: true })

    const { data: { session } } = await supabase.auth.getSession()

    if (session) {
      const meta = session.user?.user_metadata ?? {}
      set({
        token: session.access_token,
        isAuthenticated: true,
        isLoading: false,
        user: buildUser(session.user, meta),
      })
    } else {
      set({ isLoading: false })
    }

    supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        const meta = session.user?.user_metadata ?? {}
        set({
          token: session.access_token,
          isAuthenticated: true,
          user: buildUser(session.user, meta),
        })
      } else {
        set({ user: null, token: null, isAuthenticated: false })
      }
    })
  },
}))
