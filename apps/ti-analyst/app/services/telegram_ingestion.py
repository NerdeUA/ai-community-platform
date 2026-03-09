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


async def _fetch_channel_messages(username: str, limit: int = 20) -> list[dict]:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    from app.config import settings

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise RuntimeError(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH are required. "
            "Get them at https://my.telegram.org/auth → API development tools."
        )

    client = TelegramClient(_SESSION_PATH, settings.telegram_api_id, settings.telegram_api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        raise RuntimeError(
            "Telegram session not found. Run once to create it:\n"
            "  docker exec -it <container> python3 -m app.services.telegram_login"
        )

    items = []
    try:
        entity = await client.get_entity(f"@{username.lstrip('@')}")
        messages = await client.get_messages(entity, limit=limit)
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
            })
    finally:
        await client.disconnect()

    return items


def fetch_telegram_channel(username: str, limit: int = 20) -> list[dict]:
    """Sync wrapper around the async Telethon fetch."""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_fetch_channel_messages(username, limit))
        finally:
            loop.close()
    except RuntimeError as exc:
        logger.warning("Telegram ingestion skipped for @%s: %s", username, exc)
        return []
    except Exception as exc:
        logger.error("Telegram fetch error for @%s: %s", username, exc)
        return []
