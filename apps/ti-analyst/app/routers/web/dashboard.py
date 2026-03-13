from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AnalysisRun, ThreatIntel
from app.templates_config import templates

router = APIRouter(prefix="/web", tags=["web"])

_VALID_PERIODS = {"today", "24h", "7d", "30d"}


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "24h":
        return now - timedelta(hours=24)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _build_threat_query(db, period: str, q: str, severity: str, threat_type: str,
                        vendor: str, cve: str):
    since = _period_start(period if period in _VALID_PERIODS else "today")
    query = (
        db.query(ThreatIntel)
        .filter(ThreatIntel.created_at >= since, ThreatIntel.status != "ignored")
    )
    if q:
        query = query.filter(ThreatIntel.title.ilike(f"%{q}%"))
    if severity:
        query = query.filter(ThreatIntel.severity == severity)
    if threat_type:
        query = query.filter(ThreatIntel.threat_type.ilike(f"%{threat_type}%"))
    if vendor:
        query = query.filter(ThreatIntel.affected_vendors.ilike(f"%{vendor}%"))
    if cve:
        query = query.filter(ThreatIntel.cve_ids.ilike(f"%{cve}%"))
    return query


@router.get("", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Annotated[Session, Depends(get_db)]):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    threats = (
        db.query(ThreatIntel)
        .filter(ThreatIntel.created_at >= today_start, ThreatIntel.status != "ignored")
        .order_by(ThreatIntel.created_at.desc())
        .limit(200)
        .all()
    )
    recent_runs = db.query(AnalysisRun).order_by(AnalysisRun.started_at.desc()).limit(5).all()
    critical_count = (
        db.query(ThreatIntel)
        .filter(ThreatIntel.severity == "critical", ThreatIntel.created_at >= today_start,
                ThreatIntel.status != "ignored")
        .count()
    )
    high_count = (
        db.query(ThreatIntel)
        .filter(ThreatIntel.severity == "high", ThreatIntel.created_at >= today_start,
                ThreatIntel.status != "ignored")
        .count()
    )
    return templates.TemplateResponse(request, "web/dashboard.html", {
        "threats": threats,
        "recent_runs": recent_runs,
        "critical_count": critical_count,
        "high_count": high_count,
    })


@router.get("/pipeline-progress", response_class=JSONResponse)
def pipeline_progress():
    """Return current ingestion pipeline progress for dashboard polling."""
    from app.services.progress import get as get_progress
    return JSONResponse(get_progress())


@router.get("/dashboard-data", response_class=JSONResponse)
def dashboard_data(
    db: Annotated[Session, Depends(get_db)],
    period: str = Query("today"),
    q: str = Query(""),
    severity: str = Query(""),
    threat_type: str = Query(""),
    vendor: str = Query(""),
    cve: str = Query(""),
):
    """Return filtered dashboard data as JSON for in-place DOM updates."""
    threats = (
        _build_threat_query(db, period, q, severity, threat_type, vendor, cve)
        .order_by(ThreatIntel.created_at.desc())
        .limit(500)
        .all()
    )
    since = _period_start(period if period in _VALID_PERIODS else "today")
    recent_runs = db.query(AnalysisRun).order_by(AnalysisRun.started_at.desc()).limit(5).all()
    critical_count = (
        db.query(ThreatIntel)
        .filter(ThreatIntel.severity == "critical", ThreatIntel.created_at >= since,
                ThreatIntel.status != "ignored")
        .count()
    )
    high_count = (
        db.query(ThreatIntel)
        .filter(ThreatIntel.severity == "high", ThreatIntel.created_at >= since,
                ThreatIntel.status != "ignored")
        .count()
    )
    return JSONResponse({
        "critical_count": critical_count,
        "high_count": high_count,
        "recent_runs_count": len(recent_runs),
        "threats": [
            {
                "id": str(t.id),
                "title": t.title or "Unknown",
                "source_name": t.source_name or "—",
                "severity": t.severity or "",
                "threat_type": t.threat_type or "—",
                "cve_ids": t.cve_ids or "—",
                "affected_vendors_label": t.affected_vendors_label,
                "affected_assets_count": t.affected_assets_count,
                "created_at": t.created_at.strftime("%m-%d %H:%M"),
            }
            for t in threats
        ],
        "runs": [
            {
                "id": str(r.id),
                "started_at": r.started_at.strftime("%Y-%m-%d %H:%M"),
                "trigger": r.trigger,
                "status": r.status,
                "threats_processed": r.threats_processed,
                "threats_critical": r.threats_critical,
                "error_message": r.error_message or "",
            }
            for r in recent_runs
        ],
    })


@router.post("/trigger-ingestion", response_class=JSONResponse)
def trigger_ingestion():
    """Manually trigger the ingestion pipeline immediately."""
    from app.services.scheduler import trigger_ingestion_now
    started = trigger_ingestion_now()
    if started:
        return JSONResponse({"ok": True, "message": "Pipeline triggered"})
    return JSONResponse({"ok": False, "message": "Pipeline is already running"}, status_code=409)
