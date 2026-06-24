"""
app/core/locale.py — Multi-country localisation config and fiscal document validators.

Supported countries: PT (Portugal), BR (Brazil).

Validators implement full checksum verification:
  - NIF    (Portugal, 9 digits)
  - CPF    (Brazil, 11 digits)
  - CNPJ   (Brazil, 14 digits)

Entity distinction (clinica vs paciente) determines which document type applies
for BR clinics (CNPJ for clinic, CPF for patient).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ─── Config ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LocaleConfig:
    pais: str
    moeda: str                       # "EUR" | "BRL"
    simbolo_moeda: str               # "€" | "R$"
    prefixo_tel: str                 # "+351" | "+55"
    lei_privacidade: str             # "RGPD" | "LGPD"
    doc_fiscal_clinica_label: str    # "NIF" | "CNPJ"
    doc_fiscal_paciente_label: str   # "NIF" | "CPF"
    placeholder_doc_clinica: str
    placeholder_doc_paciente: str
    placeholder_tel: str


_LOCALES: dict[str, LocaleConfig] = {
    "PT": LocaleConfig(
        pais="PT",
        moeda="EUR",
        simbolo_moeda="€",
        prefixo_tel="+351",
        lei_privacidade="RGPD",
        doc_fiscal_clinica_label="NIF",
        doc_fiscal_paciente_label="NIF",
        placeholder_doc_clinica="500 000 000",
        placeholder_doc_paciente="123 456 789",
        placeholder_tel="+351 210 000 000",
    ),
    "BR": LocaleConfig(
        pais="BR",
        moeda="BRL",
        simbolo_moeda="R$",
        prefixo_tel="+55",
        lei_privacidade="LGPD",
        doc_fiscal_clinica_label="CNPJ",
        doc_fiscal_paciente_label="CPF",
        placeholder_doc_clinica="00.000.000/0001-00",
        placeholder_doc_paciente="000.000.000-00",
        placeholder_tel="+55 11 99999-9999",
    ),
}


def get_locale(pais: str) -> LocaleConfig:
    try:
        return _LOCALES[pais.upper()]
    except KeyError:
        raise ValueError(f"País não suportado: '{pais}'. Use 'PT' ou 'BR'.")


# ─── Validators ──────────────────────────────────────────────────────────────


def _digits(s: str) -> str:
    """Strip all non-digit characters."""
    return re.sub(r"\D", "", s)


def validar_nif_pt(valor: str) -> bool:
    """
    NIF Portugal — 9 digits with mod-11 check digit.
    Returns True when valid, False otherwise.
    """
    d = _digits(valor)
    if len(d) != 9:
        return False
    soma = sum(int(d[i]) * (9 - i) for i in range(8))
    resto = soma % 11
    esperado = 0 if resto < 2 else 11 - resto
    return int(d[8]) == esperado


def validar_cpf_br(valor: str) -> bool:
    """
    CPF Brazil — 11 digits with two verifier digits.
    Rejects all-same-digit sequences (e.g. 111.111.111-11).
    """
    d = _digits(valor)
    if len(d) != 11 or len(set(d)) == 1:
        return False

    soma1 = sum(int(d[i]) * (10 - i) for i in range(9))
    r1 = soma1 % 11
    dig1 = 0 if r1 < 2 else 11 - r1
    if int(d[9]) != dig1:
        return False

    soma2 = sum(int(d[i]) * (11 - i) for i in range(10))
    r2 = soma2 % 11
    dig2 = 0 if r2 < 2 else 11 - r2
    return int(d[10]) == dig2


def validar_cnpj_br(valor: str) -> bool:
    """
    CNPJ Brazil — 14 digits with two verifier digits.
    Rejects all-same-digit sequences (e.g. 11.111.111/1111-11).
    """
    d = _digits(valor)
    if len(d) != 14 or len(set(d)) == 1:
        return False

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1 = sum(int(d[i]) * p1[i] for i in range(12))
    r1 = soma1 % 11
    dig1 = 0 if r1 < 2 else 11 - r1
    if int(d[12]) != dig1:
        return False

    p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma2 = sum(int(d[i]) * p2[i] for i in range(13))
    r2 = soma2 % 11
    dig2 = 0 if r2 < 2 else 11 - r2
    return int(d[13]) == dig2


def validar_documento_fiscal(
    valor: str | None,
    pais: str,
    entidade: str,  # "clinica" | "paciente"
) -> None:
    """
    Validate documento_fiscal for the given country and entity type.
    Raises ValueError on failure. No-op when valor is None or empty.
    """
    if not valor:
        return

    pais_upper = pais.upper()
    locale = get_locale(pais_upper)

    if pais_upper == "PT":
        if not validar_nif_pt(valor):
            raise ValueError(
                f"NIF inválido — o dígito verificador não confere. "
                f"Verifique o número no cartão de cidadão ou em finanças.gov.pt. "
                f"Pode também deixar este campo em branco por agora."
            )
    elif pais_upper == "BR":
        if entidade == "clinica":
            if not validar_cnpj_br(valor):
                raise ValueError(
                    f"CNPJ inválido — verifique os dígitos verificadores. "
                    f"Pode também deixar este campo em branco por agora."
                )
        else:
            if not validar_cpf_br(valor):
                raise ValueError(
                    f"CPF inválido — verifique os dígitos verificadores "
                    f"(inclua ponto e traço: 000.000.000-00). "
                    f"Pode também deixar este campo em branco por agora."
                )
    else:
        raise ValueError(f"País não suportado: '{pais}'")
