

"""
Router — classifies incoming patient messages to select the right agent.

Two-tier pipeline
-----------------
  Tier 1 · Keyword scoring  (synchronous, zero latency, no API cost)
    Pattern matching with per-keyword weights.
    If the top intent clears the keyword_threshold → done.

  Tier 2 · LLM classification  (async, claude-haiku-4-5, ~200ms)
    Used only when keywords are inconclusive or produce a low-confidence tie.
    Forces a `classify_intent` tool call so the response is always structured.

  Fallback
    Any error or tie at both tiers → TriageAgent (safest default for a clinic).

Extending the router
--------------------
  Add a new agent by updating `AgentType`, `_KEYWORD_PATTERNS`,
  and the LLM system prompt. Nothing else changes.

Usage
-----
    router = Router(api_key="...")

    result = await router.classify("estou com muita dor de cabeça")
    # RouterResult(agent=AgentType.TRIAGE, confidence=0.91, tier=Tier.KEYWORD, ...)

    result = await router.classify("quero marcar para semana que vem")
    # RouterResult(agent=AgentType.SCHEDULING, confidence=0.87, tier=Tier.LLM, ...)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

import anthropic

logger = logging.getLogger(__name__)


# ─── Types ─────────────────────────────────────────────────────────────────────

class AgentType(str, Enum):
    SCHEDULING = "SchedulingAgent"
    TRIAGE     = "TriageAgent"
    RETENTION  = "RetentionAgent"
    FALLBACK   = "TriageAgent"   # alias — fallback resolves to triage


class Tier(str, Enum):
    KEYWORD  = "keyword"
    LLM      = "llm"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class RouterResult:
    """
    Output of the router for a single message.

    agent       Which agent should handle this message.
    confidence  0.0 – 1.0. Below ~0.5 means the router was uncertain.
    reasoning   Human-readable explanation (useful for logging / debugging).
    tier        Which classification tier produced the result.
    """
    agent: AgentType
    confidence: float
    reasoning: str
    tier: Tier

    @property
    def agent_name(self) -> str:
        """String name consumed by the agent factory / webhook handler."""
        return self.agent.value

    def __str__(self) -> str:
        return (
            f"[{self.tier.value.upper()}] {self.agent_name} "
            f"(confidence={self.confidence:.0%}) — {self.reasoning}"
        )


# ─── Keyword patterns ──────────────────────────────────────────────────────────
# Each entry: (pattern, weight)
#   weight=2  → strong signal for this intent
#   weight=1  → weak / supporting signal

class _Pattern(NamedTuple):
    regex: str
    weight: int


_KEYWORD_PATTERNS: dict[AgentType, list[_Pattern]] = {
    AgentType.SCHEDULING: [
        _Pattern(r"\bagendar\b",               2),
        _Pattern(r"\bmarcar\b",                2),
        _Pattern(r"\bconsulta\b",              2),
        _Pattern(r"\bhorario\b",               2),
        _Pattern(r"\bencaixar\b",              2),
        _Pattern(r"\bremar[ck]ar\b",           2),
        _Pattern(r"\bcancelar\b",              1),
        _Pattern(r"\bdisponib",                1),
        _Pattern(r"\bagenda\b",                1),
        _Pattern(r"\bvaga\b",                  1),
        _Pattern(r"\bdia\s+\d",                1),   # "dia 15", "dia 3/6"
        _Pattern(r"\b\d{1,2}[/\-]\d{1,2}",    1),   # dates like 15/06
    ],
    AgentType.TRIAGE: [
        _Pattern(r"\bdor\b",                   2),
        _Pattern(r"\bdoi\b",                   2),
        _Pattern(r"\bsintoma",                 2),
        _Pattern(r"\bfebre\b",                 2),
        _Pattern(r"\burgenci",                 2),
        _Pattern(r"\bemergenci",               2),
        _Pattern(r"\bsangr",                   2),
        _Pattern(r"\bmachuc",                  2),
        _Pattern(r"\bmal\b",                   1),
        _Pattern(r"\bdoente\b",                1),
        _Pattern(r"\benjoo\b",                 1),
        _Pattern(r"\bvomit",                   1),
        _Pattern(r"\bnause",                   1),
        _Pattern(r"\btontur",                  1),
        _Pattern(r"\btosse\b",                 1),
        _Pattern(r"\bgripe\b",                 1),
        _Pattern(r"\binfec",                   1),
        _Pattern(r"\bpressao\b",               1),
        _Pattern(r"\bfraqueza\b",              1),
        _Pattern(r"\bdesmai",                  2),
        _Pattern(r"\bfalta\s+d[eo]\s+ar",      2),
        _Pattern(r"\bdificuldade.*respir",      2),
    ],
    AgentType.RETENTION: [
        _Pattern(r"\bcheck.?up\b",             2),
        _Pattern(r"\bpreventi",                2),
        _Pattern(r"\bacompanhamento\b",        2),
        _Pattern(r"\bretorno\b",               1),
        _Pattern(r"\bfaz\s+tempo\b",           2),
        _Pattern(r"\bsaudade\b",               1),
        _Pattern(r"\bvolt",                    1),
        _Pattern(r"\blembrete\b",              1),
        _Pattern(r"\brevis",                   1),
        _Pattern(r"\brotina\b",                1),
    ],
}

# Maximum possible score per intent (sum of all weights) — used for normalisation
_MAX_SCORES: dict[AgentType, int] = {
    intent: sum(p.weight for p in patterns)
    for intent, patterns in _KEYWORD_PATTERNS.items()
}

# ─── LLM tool definition ───────────────────────────────────────────────────────

_CLASSIFY_TOOL: dict = {
    "name": "classify_intent",
    "description": (
        "Classify the patient's message into exactly one intent category "
        "for a medical clinic chatbot."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "enum": [a.value for a in AgentType if a is not AgentType.FALLBACK],
                "description": (
                    "SchedulingAgent — patient wants to book, reschedule, or cancel an appointment.\n"
                    "TriageAgent — patient reports symptoms, pain, or health concerns.\n"
                    "RetentionAgent — patient is responding to follow-up, check-up reminder, or re-engagement."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score between 0.0 and 1.0.",
            },
            "reasoning": {
                "type": "string",
                "description": "One sentence explaining the classification decision.",
            },
        },
        "required": ["agent", "confidence", "reasoning"],
    },
}

_LLM_SYSTEM_PROMPT = """
You are an intent classifier for a Brazilian medical clinic WhatsApp chatbot.
Classify each message into exactly one category:

  SchedulingAgent   → booking, rescheduling, cancelling appointments, checking availability
  TriageAgent       → symptoms, pain, health concerns, emergencies, medication questions
  RetentionAgent    → follow-up replies, check-up reminders, re-engagement after long absence

Rules:
• When in doubt between TriageAgent and another, prefer TriageAgent (patient safety).
• Messages about "returning" that mention symptoms → TriageAgent.
• Messages about "returning" with no symptoms → SchedulingAgent.
• Short / ambiguous messages → lower confidence score.
• Always call the classify_intent tool. Never respond with plain text.
""".strip()


# ─── Router ────────────────────────────────────────────────────────────────────

class Router:
    """
    Two-tier message router: keyword scoring → LLM (only if inconclusive).

    Parameters
    ----------
    api_key             Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
    keyword_threshold   Minimum normalised keyword score [0–1] to trust tier-1.
                        Default 0.35 — deliberately low so obvious cases skip LLM.
    llm_threshold       Minimum LLM confidence [0–1] to trust tier-2 result.
                        Below this the router falls back to TriageAgent.
    """

    _LLM_MODEL = "claude-haiku-4-5"   # fast + cheap; classification doesn't need Opus

    def __init__(
        self,
        *,
        api_key: str | None = None,
        keyword_threshold: float = 0.35,
        llm_threshold: float = 0.60,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._keyword_threshold = keyword_threshold
        self._llm_threshold = llm_threshold

    # ─── Public ────────────────────────────────────────────────────────────────

    async def classify(self, message: str) -> RouterResult:
        """
        Classify `message` and return a RouterResult.
        Never raises — any failure produces a FALLBACK result.
        """
        if not message or not message.strip():
            return _fallback("Empty message.")

        normalised = _normalise(message)

        # Tier 1 — keywords
        keyword_result = self._score_keywords(normalised)
        if keyword_result is not None:
            logger.debug("Router tier-1 hit: %s", keyword_result)
            return keyword_result

        # Tier 2 — LLM
        try:
            llm_result = await self._classify_llm(message)
            if llm_result is not None:
                logger.debug("Router tier-2 hit: %s", llm_result)
                return llm_result
        except Exception:
            logger.exception("LLM classification failed; falling back to triage.")

        return _fallback("Both tiers inconclusive.")

    def classify_sync(self, message: str) -> RouterResult:
        """
        Keyword-only synchronous classification.
        Useful for tests or contexts where async is unavailable.
        Falls back to triage when keywords are inconclusive.
        """
        if not message or not message.strip():
            return _fallback("Empty message.")
        result = self._score_keywords(_normalise(message))
        return result if result is not None else _fallback("Keywords inconclusive.")

    # ─── Tier 1 — Keyword scoring ───────────────────────────────────────────────

    def _score_keywords(self, normalised: str) -> RouterResult | None:
        """
        Score each intent against `normalised` text.
        Returns a RouterResult only if the top score clears `keyword_threshold`.
        """
        scores: dict[AgentType, float] = {}
        hits: dict[AgentType, list[str]] = {}

        for intent, patterns in _KEYWORD_PATTERNS.items():
            raw_score = 0
            matched: list[str] = []
            for pattern in patterns:
                if re.search(pattern.regex, normalised):
                    raw_score += pattern.weight
                    matched.append(pattern.regex)
            max_score = _MAX_SCORES[intent]
            scores[intent] = raw_score / max_score if max_score else 0.0
            hits[intent] = matched

        best = max(scores, key=lambda k: scores[k])
        best_score = scores[best]

        if best_score < self._keyword_threshold:
            return None

        # Detect a tie — two intents within 0.05 of each other → send to LLM
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2 and (sorted_scores[0] - sorted_scores[1]) < 0.05:
            logger.debug("Keyword tie detected (%.2f vs %.2f) — escalating to LLM.",
                         sorted_scores[0], sorted_scores[1])
            return None

        matched_patterns = hits[best]
        reasoning = (
            f"Keyword match: {', '.join(matched_patterns[:3])}"
            + (f" (+{len(matched_patterns) - 3} more)" if len(matched_patterns) > 3 else "")
        )
        return RouterResult(
            agent=best,
            confidence=min(best_score, 1.0),
            reasoning=reasoning,
            tier=Tier.KEYWORD,
        )

    # ─── Tier 2 — LLM classification ───────────────────────────────────────────

    async def _classify_llm(self, message: str) -> RouterResult | None:
        """
        Ask claude-haiku-4-5 to classify the message via forced tool call.
        Returns None if confidence is below `llm_threshold`.
        """
        response = await self._client.messages.create(
            model=self._LLM_MODEL,
            max_tokens=256,
            system=_LLM_SYSTEM_PROMPT,
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "tool", "name": "classify_intent"},
            messages=[{"role": "user", "content": message}],
        )

        tool_block = next(
            (b for b in response.content if hasattr(b, "type") and b.type == "tool_use"),
            None,
        )
        if tool_block is None:
            logger.warning("LLM returned no tool call.")
            return None

        inp = tool_block.input
        raw_agent = inp.get("agent", "")
        confidence = float(inp.get("confidence", 0.0))
        reasoning = str(inp.get("reasoning", "LLM classification."))

        try:
            agent = AgentType(raw_agent)
        except ValueError:
            logger.warning("LLM returned unknown agent '%s'.", raw_agent)
            return None

        if confidence < self._llm_threshold:
            logger.debug(
                "LLM confidence %.2f below threshold %.2f — falling back.",
                confidence, self._llm_threshold,
            )
            return None

        return RouterResult(agent=agent, confidence=confidence,
                            reasoning=reasoning, tier=Tier.LLM)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase + strip accents so 'dor' matches 'Dor', 'dôr', 'DOR'."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _fallback(reason: str) -> RouterResult:
    return RouterResult(
        agent=AgentType.TRIAGE,
        confidence=0.0,
        reasoning=f"Fallback — {reason}",
        tier=Tier.FALLBACK,
    )
