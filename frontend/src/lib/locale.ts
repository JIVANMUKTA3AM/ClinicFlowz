/**
 * locale.ts — Multi-country localisation config for the CRM frontend.
 *
 * Usage:
 *   import { getLocale } from "../lib/locale"
 *   const loc = getLocale(clinica.pais)  // "PT" | "BR"
 *   <label>{loc.docFiscalPacienteLabel}</label>
 */

export type Pais = "PT" | "BR"

export interface LocaleConfig {
  pais: Pais
  moeda: string               // "EUR" | "BRL"
  simboloMoeda: string        // "€" | "R$"
  prefixoTel: string          // "+351" | "+55"
  leiPrivacidade: string      // "RGPD" | "LGPD"
  docFiscalClinicaLabel: string   // "NIF" | "CNPJ"
  docFiscalPacienteLabel: string  // "NIF" | "CPF"
  placeholderDocClinica: string
  placeholderDocPaciente: string
  placeholderTel: string
  currencyLocale: string      // for Intl.NumberFormat / toLocaleString
}

const LOCALES: Record<Pais, LocaleConfig> = {
  PT: {
    pais: "PT",
    moeda: "EUR",
    simboloMoeda: "€",
    prefixoTel: "+351",
    leiPrivacidade: "RGPD",
    docFiscalClinicaLabel: "NIF",
    docFiscalPacienteLabel: "NIF",
    placeholderDocClinica: "500 000 000",
    placeholderDocPaciente: "123 456 789",
    placeholderTel: "+351 210 000 000",
    currencyLocale: "pt-PT",
  },
  BR: {
    pais: "BR",
    moeda: "BRL",
    simboloMoeda: "R$",
    prefixoTel: "+55",
    leiPrivacidade: "LGPD",
    docFiscalClinicaLabel: "CNPJ",
    docFiscalPacienteLabel: "CPF",
    placeholderDocClinica: "00.000.000/0001-00",
    placeholderDocPaciente: "000.000.000-00",
    placeholderTel: "+55 11 99999-9999",
    currencyLocale: "pt-BR",
  },
}

export function getLocale(pais: string | undefined | null): LocaleConfig {
  const key = (pais ?? "PT").toUpperCase() as Pais
  return LOCALES[key] ?? LOCALES.PT
}

export function formatCurrency(value: number, pais: string): string {
  const loc = getLocale(pais)
  return value.toLocaleString(loc.currencyLocale, {
    style: "currency",
    currency: loc.moeda,
    maximumFractionDigits: 0,
  })
}
