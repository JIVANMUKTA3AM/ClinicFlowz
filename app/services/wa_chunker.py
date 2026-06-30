"""
wa_chunker.py — Humanized WhatsApp message chunking.

Splits an AI response into natural chunks (≤ 180 chars, max 4) and
calculates per-chunk typing delays that mimic a human typing speed.

Usage
-----
    from app.services.wa_chunker import split_into_chunks, calculate_delay_ms

    chunks = split_into_chunks(long_response)
    for chunk in chunks:
        delay = calculate_delay_ms(chunk)
        # send typing indicator, sleep delay, send chunk
"""

from __future__ import annotations

import random
import re

_MAX_CHUNK_CHARS = 180
_MAX_CHUNKS = 4

# Sentence-boundary pattern: split after ". " / "? " / "! " / ".\n" etc.
_SENTENCE_SPLIT = re.compile(r'(?<=[.?!])\s+')


def split_into_chunks(text: str) -> list[str]:
    """
    Split `text` into at most _MAX_CHUNKS natural chunks of ≤ _MAX_CHUNK_CHARS.

    Strategy
    --------
    1. Split on blank lines (paragraph breaks) first.
    2. If a paragraph exceeds _MAX_CHUNK_CHARS, split further on sentence
       boundaries (". " / "? " / "! ").
    3. If a single sentence still exceeds the limit, keep it whole rather
       than breaking mid-word — readability beats strict char limits.
    4. Merge very short fragments (< 20 chars) with the next chunk so we
       don't send "Ok." as a standalone message.
    5. Truncate to _MAX_CHUNKS; append any overflow to the last chunk.
    """
    if not text or not text.strip():
        return []

    # ── Step 1: paragraph split ───────────────────────────────────────────────
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text.strip()) if p.strip()]

    # ── Step 2: sentence split for long paragraphs ───────────────────────────
    raw_chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= _MAX_CHUNK_CHARS:
            raw_chunks.append(para)
        else:
            sentences = _SENTENCE_SPLIT.split(para)
            current = ""
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                candidate = (current + " " + sentence).strip() if current else sentence
                if len(candidate) <= _MAX_CHUNK_CHARS:
                    current = candidate
                else:
                    if current:
                        raw_chunks.append(current)
                    # sentence alone exceeds limit → keep whole (no mid-word break)
                    current = sentence
            if current:
                raw_chunks.append(current)

    # ── Step 3: merge very short fragments ───────────────────────────────────
    merged: list[str] = []
    for chunk in raw_chunks:
        if merged and len(chunk) < 20:
            merged[-1] = merged[-1] + " " + chunk
        else:
            merged.append(chunk)

    if not merged:
        return [text.strip()]

    # ── Step 4: enforce _MAX_CHUNKS ───────────────────────────────────────────
    if len(merged) <= _MAX_CHUNKS:
        return merged

    # Collapse excess chunks into the last allowed slot
    result = merged[: _MAX_CHUNKS - 1]
    tail = " ".join(merged[_MAX_CHUNKS - 1 :])
    result.append(tail)
    return result


def calculate_delay_ms(chunk: str) -> int:
    """
    Typing delay in milliseconds for `chunk`.

    Formula
    -------
      base   = 1000ms + 40ms × len(chunk)
      jitter = uniform(−200, +200) ms
      result = clamp(base + jitter, 800, 3500)
    """
    base = 1000 + 40 * len(chunk)
    jitter = random.randint(-200, 200)
    return max(800, min(3500, base + jitter))
