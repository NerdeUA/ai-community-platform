from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AnalysisRun, ThreatIntel
from app.templates_config import templates

router = APIRouter(prefix="/web", tags=["web"])


@router.get("", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Annotated[Session, Depends(get_db)]):
    threats = db.query(ThreatIntel).order_by(ThreatIntel.created_at.desc()).limit(10).all()
    recent_runs = db.query(AnalysisRun).order_by(AnalysisRun.started_at.desc()).limit(5).all()
    critical_count = db.query(ThreatIntel).filter(ThreatIntel.severity == "critical").count()
    high_count = db.query(ThreatIntel).filter(ThreatIntel.severity == "high").count()
    return templates.TemplateResponse(request, "web/dashboard.html", {
        "threats": threats,
        "recent_runs": recent_runs,
        "critical_count": critical_count,
        "high_count": high_count,
    })
