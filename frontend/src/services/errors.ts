/**
 * errors.ts
 * Typed error handling for all service modules.
 *
 * Why a custom class?
 *   Axios errors contain raw HTTP details that are not suitable to show in the
 *   UI directly. ServiceError normalises every failure into a user-facing
 *   message + optional status code + machine-readable code for branching logic.
 */

import axios from "axios"

// ─── Error codes ──────────────────────────────────────────────────────────────

export type ErrorCode =
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "VALIDATION_ERROR"
  | "SERVER_ERROR"
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "UNKNOWN"

// ─── Custom error class ───────────────────────────────────────────────────────

export class ServiceError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code: ErrorCode = "UNKNOWN",
    /** Raw backend detail (for debug / logging) */
    public readonly detail?: unknown,
  ) {
    super(message)
    this.name = "ServiceError"
    // Maintain proper prototype chain (TS class extends Error)
    Object.setPrototypeOf(this, ServiceError.prototype)
  }

  get isNotFound()    { return this.code === "NOT_FOUND" }
  get isConflict()    { return this.code === "CONFLICT" }
  get isValidation()  { return this.code === "VALIDATION_ERROR" }
  get isUnauthorized(){ return this.code === "UNAUTHORIZED" }
}

// ─── Error factory ────────────────────────────────────────────────────────────

/**
 * Call inside every service catch block.
 * Always throws — return type is `never` so callers stay type-safe.
 */
export function handleError(error: unknown): never {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    const body   = error.response?.data
    // FastAPI returns `detail` as string or array of validation objects
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((d: { msg?: string }) => d.msg ?? String(d)).join("; ")
      : body?.detail ?? null

    if (error.code === "ECONNABORTED") {
      throw new ServiceError(
        "O pedido demorou demasiado. Verifique a ligação e tente novamente.",
        undefined, "TIMEOUT",
      )
    }

    if (!error.response) {
      throw new ServiceError(
        "Sem ligação ao servidor. Verifique a sua rede.",
        undefined, "NETWORK_ERROR",
      )
    }

    switch (status) {
      case 401:
        throw new ServiceError(
          "Sessão expirada. Por favor, inicie sessão novamente.",
          401, "UNAUTHORIZED", detail,
        )
      case 403:
        throw new ServiceError(
          "Sem permissão para realizar esta operação.",
          403, "FORBIDDEN", detail,
        )
      case 404:
        throw new ServiceError(
          detail ?? "Recurso não encontrado.",
          404, "NOT_FOUND", detail,
        )
      case 409:
        throw new ServiceError(
          detail ?? "Conflito: o recurso já existe.",
          409, "CONFLICT", detail,
        )
      case 422:
        throw new ServiceError(
          detail ?? "Dados inválidos. Verifique os campos e tente novamente.",
          422, "VALIDATION_ERROR", detail,
        )
      case 500:
      case 502:
      case 503:
        throw new ServiceError(
          "Erro interno do servidor. Tente novamente mais tarde.",
          status, "SERVER_ERROR", detail,
        )
      default:
        throw new ServiceError(
          detail ?? `Erro HTTP ${status}.`,
          status, "UNKNOWN", detail,
        )
    }
  }

  // Non-Axios error (programming error, JSON parse, etc.)
  const msg = error instanceof Error ? error.message : "Erro inesperado."
  throw new ServiceError(msg, undefined, "UNKNOWN", error)
}

// ─── Type guard ───────────────────────────────────────────────────────────────

export function isServiceError(e: unknown): e is ServiceError {
  return e instanceof ServiceError
}
