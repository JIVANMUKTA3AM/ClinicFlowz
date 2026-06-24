import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import { useAuth }                                   from "./hooks/useAuth"
import { ProtectedRoute, OnboardingRoute }           from "./components/auth/ProtectedRoute"
import { Sidebar }                                   from "./components/layout/Sidebar"
import { Topbar }                                    from "./components/layout/Topbar"
import { Login }      from "./pages/Login"
import { Register }   from "./pages/Register"
import { Onboarding } from "./pages/Onboarding"
import { Dashboard }   from "./pages/Dashboard"
import { Pacientes }   from "./pages/Pacientes"
import { Agenda }      from "./pages/Agenda"
import { Pipeline }    from "./pages/Pipeline"
import { Chat }        from "./pages/Chat"
import { Medicos }     from "./pages/Medicos"
import { Salas }       from "./pages/Salas"
import { Financeiro }      from "./pages/Financeiro"
import { Configuracoes }   from "./pages/Configuracoes"

const qc = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

const PAGE_TITLES: Record<string, string> = {
  "/dashboard":  "Dashboard",
  "/pacientes":  "Pacientes",
  "/agenda":     "Agenda",
  "/pipeline":   "Pipeline",
  "/whatsapp":   "WhatsApp",
  "/medicos":    "Médicos",
  "/salas":      "Salas",
  "/financeiro":    "Financeiro",
  "/configuracoes": "Configurações",
}

function AppLayout({ children, path }: { children: React.ReactNode; path: string }) {
  return (
    <div className="flex h-screen bg-surface-50 overflow-hidden">
      <Sidebar />
      <div className="flex-1 ml-56 flex flex-col overflow-hidden">
        <Topbar title={PAGE_TITLES[path]} />
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-screen-xl mx-auto px-6 py-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}

function AuthInitializer({ children }: { children: React.ReactNode }) {
  // Restores Supabase session on first render and subscribes to auth events
  useAuth()
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthInitializer>
          <Routes>
            {/* Public */}
            <Route path="/login"    element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Semi-protected: autenticado mas sem clinica_id */}
            <Route element={<OnboardingRoute />}>
              <Route path="/onboarding" element={<Onboarding />} />
            </Route>

            {/* Protected: autenticado + clinica_id */}
            <Route element={<ProtectedRoute />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route
                path="/dashboard"
                element={<AppLayout path="/dashboard"><Dashboard /></AppLayout>}
              />
              <Route
                path="/pacientes"
                element={<AppLayout path="/pacientes"><Pacientes /></AppLayout>}
              />
              <Route
                path="/agenda"
                element={<AppLayout path="/agenda"><Agenda /></AppLayout>}
              />
              <Route
                path="/pipeline"
                element={<AppLayout path="/pipeline"><Pipeline /></AppLayout>}
              />
              <Route
                path="/whatsapp"
                element={<AppLayout path="/whatsapp"><Chat /></AppLayout>}
              />
              <Route
                path="/medicos"
                element={<AppLayout path="/medicos"><Medicos /></AppLayout>}
              />
              <Route
                path="/salas"
                element={<AppLayout path="/salas"><Salas /></AppLayout>}
              />
              <Route
                path="/financeiro"
                element={<AppLayout path="/financeiro"><Financeiro /></AppLayout>}
              />
              <Route
                path="/configuracoes"
                element={<AppLayout path="/configuracoes"><Configuracoes /></AppLayout>}
              />
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AuthInitializer>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
