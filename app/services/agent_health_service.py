"""
agent_health_service.py — Detecção de flags de qualidade e agregação de métricas.

detect_flags   — analisa o tool_log e a resposta de um turno → dict com 4 booleanos
compute_metrics — agrega rows de wa_agent_runs → dict de saúde do agente
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from supabase import Client

# ─── Flag detection ───────────────────────────────────────────────────────────

# Matches R$ 800, €150, 9h, 09:30, 14h30
_RE_FACT = re.compile(r'R\$\s*\d|€\s*\d|\b\d{1,2}h\d{0,2}\b|\b\d{2}:\d{2}\b', re.IGNORECASE)

# CPF: 000.000.000-00
_RE_CPF = re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b')

# Email
_RE_EMAIL = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')


def detect_flags(tool_log: list[dict], response: str) -> dict:
    """
    Returns quality flags for one agent run.

    kb_miss:            search_kb was called but returned no results
    hallucination_flag: response contains concrete facts (price/time) without KB search
    handover_triggered: escalar_para_humano was called
    pii_blocked:        response contains CPF or e-mail pattern (LGPD risk)
    """
    tool_names = [t.get("tool", "") for t in tool_log]

    # kb_miss — search_kb returned empty
    kb_miss = any(
        t.get("tool") == "search_kb"
        and "Nenhuma informação" in (t.get("result_preview") or "")
        for t in tool_log
    )

    # hallucination_flag — concrete fact in response, KB not consulted
    hallucination_flag = (
        bool(_RE_FACT.search(response))
        and "search_kb" not in tool_names
    )

    # handover_triggered
    handover_triggered = "escalar_para_humano" in tool_names

    # pii_blocked — PII detected in agent output
    pii_blocked = bool(_RE_CPF.search(response) or _RE_EMAIL.search(response))

    return {
        "kb_miss":            kb_miss,
        "hallucination_flag": hallucination_flag,
        "handover_triggered": handover_triggered,
        "pii_blocked":        pii_blocked,
    }


# ─── Metrics aggregation ──────────────────────────────────────────────────────

def compute_metrics(runs: list[dict]) -> dict:
    """
    Aggregates a list of wa_agent_runs rows into health metrics.
    All rates are percentages (0–100).
    """
    n = len(runs)
    if n == 0:
        return {
            "total_runs":        0,
            "sandbox_runs":      0,
            "production_runs":   0,
            "total_cost_usd":    0.0,
            "avg_cost_usd":      0.0,
            "avg_latency_ms":    0.0,
            "p95_latency_ms":    0.0,
            "total_tokens_in":   0,
            "total_tokens_out":  0,
            "kb_miss_rate":      0.0,
            "hallucination_rate": 0.0,
            "handover_rate":     0.0,
            "pii_rate":          0.0,
        }

    sandbox_n    = sum(1 for r in runs if r.get("source") == "sandbox")
    production_n = n - sandbox_n

    total_cost = sum(float(r.get("cost_usd") or 0) for r in runs)
    latencies  = [int(r.get("latency_ms") or 0) for r in runs if r.get("latency_ms")]
    avg_lat    = sum(latencies) / len(latencies) if latencies else 0.0
    p95_lat    = _percentile(latencies, 0.95) if latencies else 0.0

    total_in  = sum(int(r.get("input_tokens")  or 0) for r in runs)
    total_out = sum(int(r.get("output_tokens") or 0) for r in runs)

    def rate(field: str) -> float:
        return round(sum(1 for r in runs if r.get(field)) / n * 100, 1)

    return {
        "total_runs":         n,
        "sandbox_runs":       sandbox_n,
        "production_runs":    production_n,
        "total_cost_usd":     round(total_cost, 4),
        "avg_cost_usd":       round(total_cost / n, 6) if n else 0.0,
        "avg_latency_ms":     round(avg_lat, 0),
        "p95_latency_ms":     round(p95_lat, 0),
        "total_tokens_in":    total_in,
        "total_tokens_out":   total_out,
        "kb_miss_rate":       rate("kb_miss"),
        "hallucination_rate": rate("hallucination_flag"),
        "handover_rate":      rate("handover_triggered"),
        "pii_rate":           rate("pii_blocked"),
    }


def _percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ─── DB query ────────────────────────────────────────────────────────────────

def fetch_runs(db: Client, clinica_id: str, days: int) -> list[dict]:
    """Fetches agent runs for this clinic in the last `days` days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    res = (
        db.table("wa_agent_runs")
        .select(
            "source, cost_usd, latency_ms, input_tokens, output_tokens, "
            "kb_miss, hallucination_flag, handover_triggered, pii_blocked, "
            "stage_before, stage_after, created_at"
        )
        .eq("clinica_id", clinica_id)
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []
