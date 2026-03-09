import logging
import uuid
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import ThreatSource
from app.services.telegram_resolver import TelegramResolverError, resolve_channel
from app.templates_config import templates

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])
logger = logging.getLogger(__name__)

SOURCE_TYPES = ["rss", "telegram", "url", "reddit"]


def _is_valid_url(url: str) -> bool:
    try:
        r = urlparse(url)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except Exception:
        return False


@router.get("", response_class=HTMLResponse)
def list_sources(request: Request, db: Annotated[Session, Depends(get_db)]):
    sources = db.query(ThreatSource).order_by(ThreatSource.name).all()
    tg_configured = bool(settings.telegram_bot_token)
    return templates.TemplateResponse(
        request,
        "admin/sources.html",
        {"sources": sources, "source_types": SOURCE_TYPES, "tg_configured": tg_configured},
    )


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
