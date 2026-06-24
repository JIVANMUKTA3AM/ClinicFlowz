/**
 * http.ts
 * Single Axios instance shared by all service modules.
 *
 * Responsibilities:
 *   - Set baseURL from VITE_API_URL env var
 *   - Inject Supabase JWT before every request
 *   - Translate HTTP 401 → sign-out + redirect
 *
 * Nothing else. Business logic belongs in individual service files.
 */

import axios from "axios"
import { supabase } from "../lib/supabase"

const http = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 15_000,
})

// ── JWT injection ──────────────────────────────────────────────────────────────

http.interceptors.request.use(async (config) => {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }
  return config
})

// ── 401 handler ───────────────────────────────────────────────────────────────

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      await supabase.auth.signOut()
      window.location.href = "/login"
    }
    return Promise.reject(error)
  },
)

export default http
