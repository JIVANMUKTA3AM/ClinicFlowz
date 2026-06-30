import http from "./http"
import { handleError } from "./errors"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PlaybookStage {
  id: string
  label: string
  goals: string[]
  probing_questions: string[]
  advance_when: string[]
  min_turns: number
  blocked_tools: string[]
}

export interface PlaybookObjection {
  name: string
  patterns: string[]
  strategy: string
  next_action: string
}

export interface AgentPlaybook {
  stages: PlaybookStage[]
  objections: PlaybookObjection[]
}

export interface WaAgent {
  id: string
  clinica_id: string
  nome: string
  ativo: boolean
  agent_playbook: AgentPlaybook
  created_at: string
  updated_at: string
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const agentesService = {
  async get(): Promise<WaAgent> {
    try {
      const res = await http.get("/api/v1/agents/")
      return res.data as WaAgent
    } catch (e) {
      throw handleError(e)
    }
  },

  async updatePlaybook(agentId: string, playbook: AgentPlaybook): Promise<WaAgent> {
    try {
      const res = await http.put(`/api/v1/agents/${agentId}/playbook`, { playbook })
      return res.data as WaAgent
    } catch (e) {
      throw handleError(e)
    }
  },
}
