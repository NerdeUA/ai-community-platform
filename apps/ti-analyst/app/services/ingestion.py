import logging
import re
from datetime import datetime, timezone

import feedparser
import requests

from app.database import SessionLocal
from app.models.models import ThreatSource

logger = logging.getLogger(__name__)


def _username_from_source(source: ThreatSource) -> str | None:
    """Return @-free username from source fields or URL."""
    if source.telegram_username:
        return source.telegram_username.lstrip("@")
    if source.url:
        m = re.search(r"t\.me/([A-Za-z0-9_]+)", source.url)
        if m:
            return m.group(1)
    return None


def fetch_telegram(source: ThreatSource, db=None) -> list[dict]:
    """Fetch only new posts from a Telegram channel via Telethon (MTProto).

    Uses source.last_seen_msg_id as min_id so only genuinely new messages
    are returned. If the channel has no new posts, returns an empty list
    without any LLM calls downstream.
    """
    from app.services.telegram_ingestion import fetch_telegram_channel

    username = _username_from_source(source)
    if not username:
        logger.warning(
            "Telegram source %s has no username or t.me URL — cannot ingest",
            source.name,
        )
        return []

    min_id = source.last_seen_msg_id or 0
    items = fetch_telegram_channel(username, min_id=min_id)
    logger.info(
        "Telegram fetched %d new posts from @%s (min_id=%d)",
        len(items), username, min_id,
    )

    # Persist the highest seen message ID so next poll skips these
    if items and db is not None:
        max_msg_id = max(it.get("_msg_id", 0) for it in items)
        if max_msg_id > min_id:
            source.last_seen_msg_id = max_msg_id

    return items


def fetch_rss(url: str) -> list[dict]:
    """Parse an RSS/Atom feed and return normalized items."""
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:20]:
            content = entry.get("summary") or entry.get("content", [{}])[0].get("value", "")
            items.append({
                "source_url": entry.get("link", url),
                "title": entry.get("title", ""),
                "content": content,
                "published_at": entry.get("published", ""),
            })
        logger.info("RSS fetched %d items from %s", len(items), url)
        return items
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return []


def fetch_url(url: str) -> list[dict]:
    """Fetch a single URL and return its content."""
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "TIAnalyst/1.0"})
        resp.raise_for_status()
        return [{"source_url": url, "title": url, "content": resp.text[:8000], "published_at": ""}]
    except Exception as exc:
        logger.warning("URL fetch failed for %s: %s", url, exc)
        return []


def _fetch_by_source(source: ThreatSource, db=None) -> list[dict]:
    """Dispatch to the correct fetcher based on source type."""
    if source.source_type == "rss":
        return fetch_rss(source.url)
    if source.source_type == "telegram":
        return fetch_telegram(source, db=db)
    return fetch_url(source.url)


def poll_source_by_id(source_id) -> list[dict]:
    """Poll a single enabled source by ID and return raw items."""
    import uuid as _uuid
    db = SessionLocal()
    try:
        source = db.query(ThreatSource).filter(
            ThreatSource.id == _uuid.UUID(str(source_id))
        ).first()
        if not source or not source.enabled:
            return []
        items = []
        try:
            items = _fetch_by_source(source)
            for item in items:
                item["source_name"] = source.name
            source.last_polled_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            logger.error("Failed to poll source %s: %s", source.name, exc)
            source.last_error_at = datetime.now(timezone.utc)
            db.commit()
        return items
    finally:
        db.close()


def poll_sources(progress_cb=None) -> list[dict]:
    """Poll all enabled sources and return raw items.

    progress_cb(done, total, current_source) is called before each source fetch.
    """
    db = SessionLocal()
    try:
        sources = db.query(ThreatSource).filter(ThreatSource.enabled == True).all()  # noqa: E712
        total = len(sources)
        all_items = []
        for idx, source in enumerate(sources):
            if progress_cb:
                progress_cb(done=idx, total=total, current=source.name)
            try:
                items = _fetch_by_source(source, db=db)
                for item in items:
                    item["source_name"] = source.name
                all_items.extend(items)
                source.last_polled_at = datetime.now(timezone.utc)
                db.commit()
            except Exception as exc:
                logger.error("Failed to poll source %s: %s", source.name, exc)
                source.last_error_at = datetime.now(timezone.utc)
                db.commit()
        if progress_cb:
            progress_cb(done=total, total=total, current="")
        return all_items
    finally:
        db.close()
