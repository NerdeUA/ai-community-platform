import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlparse, quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import ThreatIntel, ThreatSource
from app.services.telegram_resolver import TelegramResolverError, resolve_channel
from app.templates_config import templates

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])
# Security: all /admin/* routes are protected by Traefik edge-auth middleware
# (compose.agent-ti-analyst.yaml → traefik.http.routers.ti-analyst-agent.middlewares=edge-auth@docker).
# Application-level auth is intentionally absent — auth is enforced at the infrastructure layer.
logger = logging.getLogger(__name__)

SOURCE_TYPES = ["rss", "telegram", "url", "reddit"]


def _is_valid_url(url: str) -> bool:
    try:
        r = urlparse(url)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except Exception:
        return False


@router.get("", response_class=HTMLResponse)
def list_sources(request: Request, db: Annotated[Session, Depends(get_db)],
                 import_msg: str = ""):
    sources = db.query(ThreatSource).order_by(ThreatSource.name).all()
    tg_configured = bool(settings.telegram_bot_token)

    stats_rows = (
        db.query(
            ThreatIntel.source_name,
            func.count(ThreatIntel.id).label("total"),
            func.max(ThreatIntel.created_at).label("last_at"),
        )
        .group_by(ThreatIntel.source_name)
        .all()
    )
    source_stats = {
        row.source_name: {"total": row.total, "last_at": row.last_at}
        for row in stats_rows
    }

    return templates.TemplateResponse(
        request,
        "admin/sources.html",
        {
            "sources": sources,
            "source_types": SOURCE_TYPES,
            "tg_configured": tg_configured,
            "source_stats": source_stats,
            "now_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "import_msg": import_msg,
        },
    )


@router.get("/export")
def export_sources(db: Annotated[Session, Depends(get_db)]):
    """Export all configured sources as a downloadable JSON file."""
    sources = db.query(ThreatSource).order_by(ThreatSource.name).all()
    data = []
    for s in sources:
        entry: dict = {
            "name": s.name,
            "source_type": s.source_type,
            "poll_interval_minutes": s.poll_interval_minutes,
            "enabled": s.enabled,
        }
        if s.source_type == "telegram":
            entry["telegram_id"] = s.telegram_id
            entry["telegram_username"] = s.telegram_username or ""
            entry["telegram_title"] = s.telegram_title or ""
        else:
            entry["url"] = s.url or ""
        data.append(entry)

    filename = f"ti-analyst-sources-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_sources(request: Request, db: Annotated[Session, Depends(get_db)],
                         file: UploadFile = File(...)):
    """Import sources from an uploaded JSON file. Skips duplicates."""
    def _err(msg: str):
        return RedirectResponse(f"/admin/sources?import_msg={quote(msg)}", status_code=303)

    try:
        raw = await file.read()
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        return _err(f"❌ Invalid file: {exc}")

    if not isinstance(data, list):
        return _err("❌ JSON must be an array of source objects")

    added = skipped = 0
    entry_errors: list[str] = []

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            skipped += 1
            continue

        name = (entry.get("name") or "").strip()
        source_type = (entry.get("source_type") or "").strip().lower()
        if not name or source_type not in SOURCE_TYPES:
            entry_errors.append(f"item {i + 1}: missing name or unknown type '{source_type}'")
            skipped += 1
            continue

        poll_interval = max(10, int(entry.get("poll_interval_minutes") or 60))
        enabled = bool(entry.get("enabled", True))

        if source_type == "telegram":
            telegram_id = entry.get("telegram_id")
            if not telegram_id:
                entry_errors.append(f"item {i + 1} ({name}): missing telegram_id")
                skipped += 1
                continue
            if db.query(ThreatSource).filter(ThreatSource.telegram_id == int(telegram_id)).first():
                skipped += 1
                continue
            s = ThreatSource(
                name=name,
                source_type="telegram",
                telegram_id=int(telegram_id),
                telegram_title=entry.get("telegram_title") or None,
                telegram_username=entry.get("telegram_username") or None,
                poll_interval_minutes=poll_interval,
                enabled=enabled,
            )
        else:
            url = (entry.get("url") or "").strip()
            if not _is_valid_url(url):
                entry_errors.append(f"item {i + 1} ({name}): invalid URL")
                skipped += 1
                continue
            if db.query(ThreatSource).filter(ThreatSource.url == url).first():
                skipped += 1
                continue
            s = ThreatSource(
                name=name,
                source_type=source_type,
                url=url,
                poll_interval_minutes=poll_interval,
                enabled=enabled,
            )

        db.add(s)
        db.flush()
        added += 1

    db.commit()

    parts = [f"✅ Added {added} source(s)"]
    if skipped:
        parts.append(f"{skipped} skipped (duplicates or invalid)")
    if entry_errors:
        parts.append("Errors: " + "; ".join(entry_errors[:3]))
    return _err(" — ".join(parts))  # reuse _err for redirect; msg may be success too


@router.post("/resolve-telegram", response_class=JSONResponse)
async def resolve_telegram(request: Request):
    """Resolve a Telegram channel identifier via Bot API and return its metadata as JSON."""
    body = await request.json()
    channel_input: str = (body.get("channel_input") or "").strip()
    if not channel_input:
        return JSONResponse({"error": "channel_input is required"}, status_code=400)

    try:
        info = resolve_channel(channel_input, bot_token=settings.telegram_bot_token)
    except TelegramResolverError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        logger.exception("Unexpected error resolving Telegram channel")
        return JSONResponse({"error": f"Unexpected error: {e}"}, status_code=500)

    return JSONResponse({
        "telegram_id": info.telegram_id,
        "full_id": info.full_id,
        "title": info.title,
        "username": info.username,
        "description": info.description,
        "member_count": info.member_count,
    })


@router.post("/verify-rss", response_class=JSONResponse)
async def verify_rss(request: Request):
    """Fetch an RSS/Atom feed and return its metadata for pre-flight validation."""
    import feedparser

    body = await request.json()
    url: str = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)
    if not _is_valid_url(url):
        return JSONResponse({"error": "URL must start with http:// or https://"}, status_code=400)

    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        return JSONResponse({"error": f"Failed to fetch feed: {exc}"}, status_code=422)

    # bozo=True means the parser hit a fatal error AND there are no entries
    if feed.get("bozo") and not feed.get("entries"):
        err = str(feed.get("bozo_exception", "malformed feed"))
        return JSONResponse({"error": f"Invalid RSS/Atom feed: {err}"}, status_code=422)

    if not feed.get("feed") and not feed.get("entries"):
        return JSONResponse({"error": "No RSS/Atom content found at this URL"}, status_code=422)

    title = (feed.feed.get("title") or "").strip()
    description = (
        feed.feed.get("description") or feed.feed.get("subtitle") or ""
    ).strip()
    entry_count = len(feed.entries)

    return JSONResponse({
        "title": title,
        "description": description,
        "entry_count": entry_count,
    })


@router.post("/create")
def create_source(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    name: str = Form(...),
    source_type: str = Form("rss"),
    url: str = Form(""),
    poll_interval_minutes: int = Form(60),
    telegram_id: int = Form(0),
    telegram_title: str = Form(""),
    telegram_username: str = Form(""),
):
    def _error(msg: str):
        sources = db.query(ThreatSource).order_by(ThreatSource.name).all()
        tg_configured = bool(settings.telegram_bot_token)
        return templates.TemplateResponse(
            request,
            "admin/sources.html",
            {"sources": sources, "source_types": SOURCE_TYPES, "tg_configured": tg_configured, "error": msg},
            status_code=400,
        )

    if source_type == "telegram":
        if not telegram_id:
            return _error("Telegram channel must be resolved before saving. Use the Resolve button.")
        s = ThreatSource(
            name=name,
            source_type="telegram",
            telegram_id=telegram_id,
            telegram_title=telegram_title or None,
            telegram_username=telegram_username or None,
            poll_interval_minutes=poll_interval_minutes,
        )
    else:
        if not _is_valid_url(url):
            return _error("URL must start with http:// or https://")
        s = ThreatSource(name=name, source_type=source_type, url=url, poll_interval_minutes=poll_interval_minutes)

    db.add(s)
    db.commit()
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/{source_id}/poll", response_class=JSONResponse)
def poll_source(source_id: str, db: Annotated[Session, Depends(get_db)]):
    """Force-fetch a single source and run items through the pipeline."""
    s = db.query(ThreatSource).filter(ThreatSource.id == uuid.UUID(source_id)).first()
    if not s:
        return JSONResponse({"error": "Source not found"}, status_code=404)
    if not s.enabled:
        return JSONResponse({"error": "Source is disabled"}, status_code=400)
    from app.services.scheduler import run_pipeline_for_source
    result = run_pipeline_for_source(source_id)
    if "error" in result:
        already_running = "already" in result["error"]
        return JSONResponse(result, status_code=409 if already_running else 500)
    return JSONResponse(result)


@router.post("/{source_id}/update")
def update_source(
    request: Request,
    source_id: str,
    db: Annotated[Session, Depends(get_db)],
    name: str = Form(...),
    url: str = Form(""),
    poll_interval_minutes: int = Form(60),
):
    s = db.query(ThreatSource).filter(ThreatSource.id == uuid.UUID(source_id)).first()
    if not s:
        return RedirectResponse("/admin/sources", status_code=303)
    s.name = name.strip()
    s.poll_interval_minutes = poll_interval_minutes
    if s.source_type != "telegram":
        if url and not _is_valid_url(url):
            sources = db.query(ThreatSource).order_by(ThreatSource.name).all()
            tg_configured = bool(settings.telegram_bot_token)
            return templates.TemplateResponse(
                request,
                "admin/sources.html",
                {"sources": sources, "source_types": SOURCE_TYPES, "tg_configured": tg_configured,
                 "error": "URL must start with http:// or https://"},
                status_code=400,
            )
        if url:
            s.url = url
    db.commit()
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/{source_id}/toggle")
def toggle_source(source_id: str, db: Annotated[Session, Depends(get_db)]):
    s = db.query(ThreatSource).filter(ThreatSource.id == uuid.UUID(source_id)).first()
    if s:
        s.enabled = not s.enabled
        db.commit()
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/{source_id}/delete")
def delete_source(source_id: str, db: Annotated[Session, Depends(get_db)]):
    s = db.query(ThreatSource).filter(ThreatSource.id == uuid.UUID(source_id)).first()
    if s:
        db.delete(s)
        db.commit()
    return RedirectResponse("/admin/sources", status_code=303)
