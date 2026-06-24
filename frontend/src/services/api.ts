/**
 * api.ts — barrel re-export
 *
 * Re-exports the shared HTTP instance and all domain services so that
 * existing imports like:
 *
 *   import { pacientesService, consultasService } from "../services/api"
 *
 * continue to work without changes.
 *
 * For new code, prefer importing directly from the domain file:
 *
 *   import { pacientesService } from "../services/pacientes.service"
 */

export { default } from "./http"
export { default as http } from "./http"
export { ServiceError, isServiceError, handleError } from "./errors"

export { pacientesService } from "./pacientes.service"
export { consultasService } from "./consultas.service"
export { agendaService }    from "./agenda.service"
export { pipelineService }  from "./pipeline.service"
export { whatsappService }  from "./whatsapp.service"

// ── Additional services (not in the original monolith) ────────────────────────
export { medicosService }   from "./medicos.service"
export { salasService }     from "./salas.service"
export { timelineService }  from "./timeline.service"
export { financeiroService } from "./financeiro.service"
export { onboardingService } from "./onboarding.service"

// ── Type re-exports (convenience) ─────────────────────────────────────────────
export type { PacienteUI, CriarPacienteDTO, AtualizarPacienteDTO } from "./pacientes.service"
export type { ConsultaUI, CriarConsultaDTO, AtualizarConsultaDTO } from "./consultas.service"
export type { KpisUI, AgendaSemanaUI, SlotUI }                     from "./agenda.service"
export type { PipelineEntryUI, FunilUI, FunilEtapaUI }             from "./pipeline.service"
export type { InteracaoUI, ConversaUI }                            from "./whatsapp.service"
