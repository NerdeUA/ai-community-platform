"""Telegram channel resolver using the Bot HTTP API (no MTProto required)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_BOT_API = "https://api.telegram.org/bot{token}/{method}"


@dataclass
class ChannelInfo:
    telegram_id: int        # positive channel ID (without -100 prefix)
    full_id: int            # as Bot API returns it, e.g. -1001234567890
    title: str
    username: str | None    # without @
    description: str | None
    member_count: int | None


class TelegramResolverError(Exception):
    pass


def normalize_input(user_input: str) -> str:
    """
    Normalise various Telegram identifier formats for getChat.

    Bot API accepts:
      @username       — public channel username
      -1001234567890  — full channel ID (with -100 prefix)
    """
    s = user_input.strip()

    # Pure negative ID — pass as-is
    if re.fullmatch(r"-\d+", s):
        return s

    # Bare positive numeric ID — add -100 prefix
    if re.fullmatch(r"\d+", s):
        numeric = int(s)
        # Heuristic: raw channel IDs are > 1_000_000_000
        return f"-100{numeric}" if numeric > 1_000_000 else s

    # Strip URL prefix
    for prefix in ("https://t.me/", "http://t.me/", "t.me/",
                   "https://telegram.me/", "telegram.me/"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break

    # Invite links (joinchat / +) cannot be resolved by getChat without joining
    if s.startswith("+") or s.lower().startswith("joinchat/"):
        raise TelegramResolverError(
            "Invite links cannot be resolved via Bot API. "
            "Use the channel @username or numeric ID instead."
        )

    # Ensure @username format
    if not s.startswith("@"):
        s = f"@{s}"

    return s


def _bot_get(token: str, method: str, **params) -> dict:
    url = _BOT_API.format(token=token, method=method)
    try:
        resp = requests.get(url, params=params, timeout=10)
    except requests.RequestException as e:
        raise TelegramResolverError(f"Network error: {e}") from e

    data = resp.json()
    if not data.get("ok"):
        code = data.get("error_code", 0)
        desc = data.get("description", "Unknown error")
        retry = (data.get("parameters") or {}).get("retry_after")
        if code == 429:
            raise TelegramResolverError(f"Rate limited by Telegram, retry after {retry}s")
        if code in (400, 403):
            raise TelegramResolverError(f"Channel not found or private: {desc}")
        raise TelegramResolverError(f"Telegram API error {code}: {desc}")

    return data["result"]


def _extract_raw_id(full_id: int) -> int:
    """Convert Bot API full ID (-1001234567890) to positive raw ID (1234567890)."""
    s = str(abs(full_id))
    return int(s[3:]) if s.startswith("100") and len(s) > 3 else abs(full_id)


def resolve_channel(user_input: str, bot_token: str) -> ChannelInfo:
    """
    Resolve a public Telegram channel by username, URL or numeric ID.

    Uses the Telegram Bot HTTP API — no MTProto or session required.
    The bot does NOT need to be a member of the channel.
    """
    if not bot_token:
        raise TelegramResolverError(
            "Telegram bot token not configured (TELEGRAM_BOT_TOKEN)"
        )

    try:
        chat_id = normalize_input(user_input)
    except TelegramResolverError:
        raise

    chat = _bot_get(bot_token, "getChat", chat_id=chat_id)

    if chat.get("type") not in ("channel", "supergroup", "group"):
        raise TelegramResolverError(
            f"Identifier points to a '{chat.get('type')}', not a channel or group"
        )

    full_id: int = chat["id"]
    raw_id = _extract_raw_id(full_id)

    # Member count (best-effort, may fail for some channels)
    member_count: int | None = chat.get("member_count")
    if member_count is None:
        try:
            member_count = _bot_get(bot_token, "getChatMemberCount", chat_id=chat_id)
        except TelegramResolverError:
            pass  # non-critical

    return ChannelInfo(
        telegram_id=raw_id,
        full_id=full_id,
        title=chat["title"],
        username=chat.get("username") or None,
        description=chat.get("description") or None,
        member_count=member_count,
    )
