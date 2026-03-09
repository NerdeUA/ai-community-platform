import logging

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def _get_chat_id() -> str:
    """Return effective chat_id: DB setting takes precedence over env var."""
    try:
        from app.database import SessionLocal
        from app.models.models import AgentSettings
        db = SessionLocal()
        try:
            s = db.query(AgentSettings).first()
            if s and s.telegram_alert_chat_id:
                return s.telegram_alert_chat_id
        finally:
            db.close()
    except Exception:
        pass
    return settings.telegram_alert_chat_id


def send_telegram_alert(message: str) -> bool:
    """Send a message to the configured Telegram alert channel."""
    if not settings.telegram_bot_token:
        logger.debug("Telegram bot token not configured, skipping alert")
        return False
    chat_id = _get_chat_id()
    if not chat_id:
        logger.debug("Telegram alert chat_id not configured, skipping alert")
        return False
    try:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Telegram alert failed: %s", exc)
        return False
