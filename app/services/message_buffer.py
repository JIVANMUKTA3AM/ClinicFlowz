"""
message_buffer.py — Debounce buffer for WhatsApp messages.

When a patient sends a burst of short messages ("oi" / "tudo bem?" / "quero
agendar"), we wait for them to finish typing before running the AI agent.
This avoids three separate agent runs for what is conceptually one turn.

Architecture
-----------
Redis (preferred):
    wa:buffer:{tenant_id}:{phone}:text  — accumulated text   (EXPIRE = ttl)
    wa:buffer:{tenant_id}:{phone}:turn  — owner UUID         (EXPIRE = ttl)

    Each new message resets both TTLs and stamps a fresh turn UUID.
    The asyncio task spawned per message sleeps for `ttl` seconds and then
    checks whether its own UUID is still current.  Only the last message's
    task fires the callback; all earlier tasks silently exit.

In-process fallback (no Redis / Redis unavailable):
    Uses asyncio.Task cancellation.  A new message cancels the pending task
    for the same (tenant, phone) pair and schedules a fresh one.
    Correct for a single uvicorn worker; breaks under multiple workers.

Usage
-----
    # once at app startup:
    await message_buffer.init(settings.REDIS_URL)

    # inside the webhook handler, per incoming message:
    await message_buffer.push(
        tenant_id=clinica_id,
        phone=telefone,
        text=texto,
        ttl=12,
        on_flush=async_callback,    # receives full accumulated text
    )
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# ─── Module state ──────────────────────────────────────────────────────────────

_redis: object | None = None                   # redis.asyncio client, set by init()
_tasks: dict[str, asyncio.Task[None]] = {}    # in-process: buffer-key → pending task
_texts: dict[str, str] = {}                   # in-process: buffer-key → accumulated text


# ─── Startup / Recovery ────────────────────────────────────────────────────────

async def init(redis_url: str) -> bool:
    """
    Try to connect to Redis.
    Returns True on success; falls back to in-process mode and returns False.
    Call once inside the FastAPI lifespan startup.
    """
    global _redis
    if not redis_url:
        logger.info("MessageBuffer: no REDIS_URL configured — using in-process fallback")
        return False
    try:
        from redis import asyncio as aioredis  # type: ignore[import]
        client = aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        await client.ping()
        _redis = client
        logger.info("MessageBuffer: Redis connected at %s", redis_url)
        return True
    except Exception as exc:
        logger.warning(
            "MessageBuffer: Redis unavailable (%s) — using in-process fallback", exc
        )
        _redis = None
        return False


async def recover(
    make_on_flush: Callable[[str, str], Callable[[str], Awaitable[None]]],
    delay: int = 5,
) -> int:
    """
    Scan Redis for orphaned buffer keys left by a previous process and
    re-schedule their flush.  Call once at startup, after init().

    make_on_flush(tenant_id, phone) must return an on_flush coroutine that
    accepts the accumulated text string.

    Returns the number of recovered buffers.
    """
    if _redis is None:
        return 0

    recovered = 0
    async for key in _redis.scan_iter("wa:buffer:*:text"):  # type: ignore[union-attr]
        # key format: wa:buffer:{tenant_id}:{phone}:text
        parts = key.split(":")
        if len(parts) != 5:
            logger.warning("MessageBuffer.recover: unexpected key shape %s — skipping", key)
            continue
        _, _, tenant_id, phone, _ = parts
        on_flush = make_on_flush(tenant_id, phone)
        asyncio.create_task(
            _recover_flush(key, on_flush, delay),
            name=f"wa-recover-{phone[:12]}",
        )
        recovered += 1
        logger.info("MessageBuffer.recover: scheduling flush for %s in %ds", key, delay)

    if recovered:
        logger.info("MessageBuffer.recover: %d orphaned buffer(s) queued", recovered)
    return recovered


async def _recover_flush(
    key_text: str,
    on_flush: Callable[[str], Awaitable[None]],
    delay: int,
) -> None:
    await asyncio.sleep(delay)

    # GETDEL atomically fetches + removes the key, preventing a double-flush
    # if a new _push_redis task fires concurrently for the same (tenant, phone).
    full_text: str = await _redis.getdel(key_text) or ""  # type: ignore[union-attr]
    if not full_text:
        return

    key_turn = key_text[: -len(":text")] + ":turn"
    await _redis.delete(key_turn)  # type: ignore[union-attr]

    try:
        await on_flush(full_text)
    except Exception:
        logger.exception("Buffer (recover): on_flush error | key=%s", key_text)


# ─── Public API ────────────────────────────────────────────────────────────────

async def push(
    *,
    tenant_id: str,
    phone: str,
    text: str,
    ttl: int,
    on_flush: Callable[[str], Awaitable[None]],
) -> None:
    """
    Append `text` to the buffer for (tenant_id, phone).
    After `ttl` seconds of inactivity, calls on_flush(accumulated_text).
    """
    if _redis is not None:
        await _push_redis(tenant_id, phone, text, ttl, on_flush)
    else:
        _push_inproc(tenant_id, phone, text, ttl, on_flush)


# ─── Redis backend ─────────────────────────────────────────────────────────────

async def _push_redis(
    tenant_id: str,
    phone: str,
    text: str,
    ttl: int,
    on_flush: Callable[[str], Awaitable[None]],
) -> None:
    key_text = f"wa:buffer:{tenant_id}:{phone}:text"
    key_turn = f"wa:buffer:{tenant_id}:{phone}:turn"
    turn_id = str(uuid.uuid4())

    existing: str = await _redis.get(key_text) or ""  # type: ignore[union-attr]
    new_text = (existing + "\n" + text).strip() if existing else text
    await _redis.set(key_text, new_text, ex=ttl)   # type: ignore[union-attr]
    await _redis.set(key_turn, turn_id, ex=ttl)    # type: ignore[union-attr]

    logger.info("Buffer: agregando mensagem de %s, turno em %ds", phone, ttl)

    asyncio.create_task(
        _redis_flush_after(key_text, key_turn, turn_id, ttl, on_flush),
        name=f"wa-buffer-{phone[:12]}",
    )


async def _redis_flush_after(
    key_text: str,
    key_turn: str,
    turn_id: str,
    ttl: int,
    on_flush: Callable[[str], Awaitable[None]],
) -> None:
    await asyncio.sleep(ttl)

    current_turn: str | None = await _redis.get(key_turn)  # type: ignore[union-attr]
    if current_turn != turn_id:
        return  # a newer message already took ownership

    full_text: str = await _redis.get(key_text) or ""   # type: ignore[union-attr]
    await _redis.delete(key_text, key_turn)              # type: ignore[union-attr]

    if not full_text:
        return

    try:
        await on_flush(full_text)
    except Exception:
        logger.exception("Buffer (redis): on_flush error | turn=%s", turn_id)


# ─── In-process backend ────────────────────────────────────────────────────────

def _push_inproc(
    tenant_id: str,
    phone: str,
    text: str,
    ttl: int,
    on_flush: Callable[[str], Awaitable[None]],
) -> None:
    key = f"{tenant_id}:{phone}"

    existing = _texts.get(key, "")
    _texts[key] = (existing + "\n" + text).strip() if existing else text

    old = _tasks.get(key)
    if old and not old.done():
        old.cancel()

    logger.info("Buffer: agregando mensagem de %s, turno em %ds", phone, ttl)

    task = asyncio.create_task(
        _inproc_flush_after(key, ttl, on_flush),
        name=f"wa-buffer-{phone[:12]}",
    )
    _tasks[key] = task


async def _inproc_flush_after(
    key: str,
    ttl: int,
    on_flush: Callable[[str], Awaitable[None]],
) -> None:
    try:
        await asyncio.sleep(ttl)
    except asyncio.CancelledError:
        return  # a newer message arrived and cancelled this task

    full_text = _texts.pop(key, "")
    _tasks.pop(key, None)

    if not full_text:
        return

    try:
        await on_flush(full_text)
    except Exception:
        logger.exception("Buffer (inproc): on_flush error | key=%s", key)
