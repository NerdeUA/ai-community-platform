"""
Telegram channel ingestion via Telethon (MTProto user session).

Reads recent posts from public Telegram channels using a user account session.
Requires TELEGRAM_API_ID, TELEGRAM_API_HASH (from my.telegram.org).

First-time setup — run once interactively to create a session:
    docker exec -it <ti-analyst-container> python3 -m app.services.telegram_login
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_SESSION_PATH = "/app/.telegram_session"


_TELETHON_CONNECT_TIMEOUT = 30   # seconds per network operation
_TELETHON_FETCH_TIMEOUT = 60    # seconds for get_messages


async def _fetch_channel_messages(username: str, limit: int = 20, min_id: int = 0) -> list[dict]:
    from telethon import TelegramClient

    from app.config import settings

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise RuntimeError(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH are required. "
            "Get them at https://my.telegram.org/auth → API development tools."
        )

    client = TelegramClient(
        _SESSION_PATH,
        settings.telegram_api_id,
        settings.telegram_api_hash,
        connection_retries=1,
        retry_delay=2,
        request_retries=1,
    )

    try:
        await asyncio.wait_for(client.connect(), timeout=_TELETHON_CONNECT_TIMEOUT)
    except asyncio.TimeoutError:
        raise RuntimeError(f"Telegram connect timed out after {_TELETHON_CONNECT_TIMEOUT}s")

    items = []
    try:
        if not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
            raise RuntimeError(
                "Telegram session not found. Run once to create it:\n"
                "  docker exec -it <container> python3 -m app.services.telegram_login"
            )

        entity = await asyncio.wait_for(
            client.get_entity(f"@{username.lstrip('@')}"),
            timeout=_TELETHON_CONNECT_TIMEOUT,
        )
        messages = await asyncio.wait_for(
            client.get_messages(entity, limit=limit, min_id=min_id),
            timeout=_TELETHON_FETCH_TIMEOUT,
        )
        channel_username = getattr(entity, "username", None) or username
        for msg in messages:
            text = msg.message or ""
            if not text.strip():
                continue
            items.append({
                "source_url": f"https://t.me/{channel_username}/{msg.id}",
                "title": f"Telegram/@{channel_username}",
                "content": text,
                "published_at": msg.date.isoformat() if msg.date else "",
                "_msg_id": msg.id,
            })
    finally:
        await asyncio.wait_for(client.disconnect(), timeout=10)

    return items


def fetch_telegram_channel(username: str, limit: int = 20, min_id: int = 0) -> list[dict]:
    """Sync wrapper around the async Telethon fetch."""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_fetch_channel_messages(username, limit, min_id=min_id))
        finally:
            loop.close()
    except RuntimeError as exc:
        logger.warning("Telegram ingestion skipped for @%s: %s", username, exc)
        return []
    except Exception as exc:
        logger.error("Telegram fetch error for @%s: %s", username, exc)
        return []
