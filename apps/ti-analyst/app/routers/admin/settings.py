from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings as cfg
from app.database import get_db
from app.models.models import AgentSettings, ThreatIntel
from app.templates_config import templates

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


@router.get("", response_class=HTMLResponse)
def get_settings(request: Request, db: Annotated[Session, Depends(get_db)]):
    s = db.query(AgentSettings).first()
    if not s:
        s = AgentSettings()
        db.add(s)
        db.commit()
        db.refresh(s)
    tg_token_set = bool(cfg.telegram_bot_token)
    # DB value takes precedence over env
    effective_chat_id = s.telegram_alert_chat_id or cfg.telegram_alert_chat_id or ""
    return templates.TemplateResponse(request, "admin/settings.html", {
        "settings": s,
        "tg_token_set": tg_token_set,
        "tg_chat_id": effective_chat_id,
    })


@router.post("/test-telegram", response_class=JSONResponse)
def test_telegram(db: Annotated[Session, Depends(get_db)]):
    """Send a test notification (last threat report or ping) to the configured chat."""
    from app.services.notifier import _get_chat_id, send_telegram_alert

    if not cfg.telegram_bot_token:
        return JSONResponse({"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}, status_code=400)
    chat_id = _get_chat_id()
    if not chat_id:
        return JSONResponse({"ok": False, "error": "Alert Chat ID not set — enter it above and save"}, status_code=400)

    threat = db.query(ThreatIntel).order_by(ThreatIntel.created_at.desc()).first()
    if threat and threat.exec_report:
        sev = (threat.severity or "unknown").upper()
        msg = (
            f"*[TEST] [{sev}] {threat.title or 'Threat Report'}*\n\n"
            f"{threat.exec_report[:3500]}"
        )
        note = f"Sent last threat report: {threat.title or str(threat.id)}"
    else:
        msg = (
            "*[TEST] Sentinel-AI TI Analyst*\n\n"
            "Bot notification is working. No threats have been analyzed yet."
        )
        note = "Sent connectivity test (no threats in DB yet)"

    ok = send_telegram_alert(msg)
    if ok:
        return JSONResponse({"ok": True, "note": note, "chat_id": chat_id})
    return JSONResponse({"ok": False, "error": "sendMessage failed — check container logs"}, status_code=500)


@router.post("/update")
def update_settings(
    db: Annotated[Session, Depends(get_db)],
    triage_model: str = Form(...),
    analyst_model: str = Form(...),
    infra_model: str = Form(...),
    ingestion_cron: str = Form(...),
    triage_prompt: str = Form(...),
    analyst_prompt: str = Form(...),
    infra_prompt: str = Form(...),
    publisher_ops_prompt: str = Form(...),
    publisher_exec_prompt: str = Form(...),
    openclaw_enabled: bool = Form(False),
    telegram_alert_chat_id: str = Form(""),
):
    s = db.query(AgentSettings).first()
    if not s:
        s = AgentSettings()
        db.add(s)
    s.triage_model = triage_model
    s.analyst_model = analyst_model
    s.infra_model = infra_model
    s.ingestion_cron = ingestion_cron
    s.triage_prompt = triage_prompt
    s.analyst_prompt = analyst_prompt
    s.infra_prompt = infra_prompt
    s.publisher_ops_prompt = publisher_ops_prompt
    s.publisher_exec_prompt = publisher_exec_prompt
    s.openclaw_enabled = openclaw_enabled
    s.telegram_alert_chat_id = telegram_alert_chat_id.strip() or None
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)
