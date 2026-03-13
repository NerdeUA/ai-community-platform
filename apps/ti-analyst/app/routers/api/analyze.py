import hashlib
import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.graph.workflow import get_graph
from app.models.models import AgentSettings, AnalysisRun, ThreatIntel
from app.services.opensearch_client import OpenSearchClient

router = APIRouter(prefix="/api/v1", tags=["api"])
logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    content: str
    source_url: str | None = None
    source_name: str | None = None


@router.post("/analyze")
def trigger_analysis(req: AnalyzeRequest, db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """Trigger a threat analysis pipeline on provided content."""
    dedup_hash = hashlib.sha256(req.content.encode()).hexdigest()[:64]
    existing = db.query(ThreatIntel).filter(ThreatIntel.dedup_hash == dedup_hash).first()
    if existing:
        return JSONResponse({"status": "duplicate", "threat_id": str(existing.id)})

    s = db.query(AgentSettings).first()
    model_config: dict = {}
    if s:
        model_config = {
            "triage_model": s.triage_model,
            "analyst_model": s.analyst_model,
            "infra_model": s.infra_model,
            "triage_prompt": s.triage_prompt,
            "analyst_prompt": s.analyst_prompt,
            "infra_prompt": s.infra_prompt,
            "publisher_ops_prompt": s.publisher_ops_prompt,
            "publisher_exec_prompt": s.publisher_exec_prompt,
        }

    run = AnalysisRun(trigger="api")
    db.add(run)
    db.commit()
    db.refresh(run)

    initial_state = {
        "raw_content": req.content,
        "metadata": {"source_url": req.source_url, "source_name": req.source_name},
        "threat_profile": {},
        "research_data": None,
        "affected_assets": [],
        "reports": {},
        "model_config": model_config,
        "status": "new",
        "ignore": False,
        "error": None,
    }

    try:
        result = get_graph().invoke(initial_state)
        if result.get("ignore"):
            run.status = "ignored"
            db.commit()
            return JSONResponse({"status": "ignored", "reason": "content not threat-relevant"})

        threat = ThreatIntel(
            source_url=req.source_url,
            source_name=req.source_name,
            raw_content=req.content[:4000],
            title=result["threat_profile"].get("title"),
            cve_ids=",".join(result["threat_profile"].get("cve_ids", [])),
            threat_type=result["threat_profile"].get("threat_type"),
            severity=result["threat_profile"].get("severity"),
            confidence=result["threat_profile"].get("confidence"),
            affected_vendors=json.dumps(result["threat_profile"].get("affected_vendors", [])),
            ops_report=result["reports"].get("ops"),
            exec_report=result["reports"].get("executive"),
            affected_assets_count=len(result.get("affected_assets", [])),
            status=result.get("status", "reported"),
            dedup_hash=dedup_hash,
            analysis_run_id=run.id,
        )
        db.add(threat)
        run.status = "completed"
        run.threats_processed = 1
        run.threats_critical = 1 if threat.severity in ("high", "critical") else 0
        db.commit()
        db.refresh(threat)

        try:
            os_client = OpenSearchClient()
            os_client.index_threat(str(threat.id), {
                "title": threat.title,
                "summary": result["threat_profile"].get("summary", ""),
                "severity": threat.severity,
                "cve_ids": threat.cve_ids,
            })
        except Exception as idx_err:
            logger.warning("OpenSearch index failed: %s", idx_err)

        return JSONResponse({
            "status": "analyzed",
            "threat_id": str(threat.id),
            "severity": threat.severity,
            "title": threat.title,
            "affected_assets": threat.affected_assets_count,
        })
    except Exception as exc:
        logger.error("Analysis failed: %s", exc)
        run.status = "error"
        run.error_message = str(exc)
        db.commit()
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)


@router.get("/threats")
def list_threats(db: Annotated[Session, Depends(get_db)], limit: int = 20, severity: str | None = None) -> JSONResponse:
    q = db.query(ThreatIntel).filter(ThreatIntel.status != "ignored")
    if severity:
        q = q.filter(ThreatIntel.severity == severity)
    threats = q.order_by(ThreatIntel.created_at.desc()).limit(limit).all()
    return JSONResponse([{
        "id": str(t.id),
        "title": t.title,
        "severity": t.severity,
        "threat_type": t.threat_type,
        "cve_ids": t.cve_ids,
        "affected_assets": t.affected_assets_count,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
    } for t in threats])


@router.post("/threats/{threat_id}/generate-reports")
def generate_reports(threat_id: str, db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """Run publisher_node on-demand for a threat that has no reports yet."""
    from app.graph.nodes import publisher_node

    threat = db.query(ThreatIntel).filter(ThreatIntel.id == uuid.UUID(threat_id)).first()
    if not threat:
        return JSONResponse({"error": "not found"}, status_code=404)
    if threat.ops_report or threat.exec_report:
        return JSONResponse({"status": "already_generated",
                             "ops_report": threat.ops_report,
                             "exec_report": threat.exec_report})

    s = db.query(AgentSettings).first()
    model_config: dict = {}
    if s:
        model_config = {
            "analyst_model": s.analyst_model,
            "publisher_ops_prompt": s.publisher_ops_prompt,
            "publisher_exec_prompt": s.publisher_exec_prompt,
        }

    try:
        vendors = json.loads(threat.affected_vendors or "[]")
    except Exception:
        vendors = []

    state = {
        "threat_profile": {
            "title": threat.title,
            "threat_type": threat.threat_type,
            "cve_ids": threat.cve_ids.split(",") if threat.cve_ids else [],
            "severity": threat.severity,
            "confidence": threat.confidence,
            "affected_vendors": vendors,
            "raw_content": threat.raw_content,
        },
        "affected_assets": [],
        "research_data": None,
        "model_config": model_config,
        "reports": {},
        "status": "analyzed",
        "ignore": False,
        "error": None,
    }

    try:
        result_state = publisher_node(state)
    except Exception as exc:
        logger.error("generate_reports failed for %s: %s", threat_id, exc)
        return JSONResponse({"error": str(exc)}, status_code=500)

    reports = result_state.get("reports", {})
    threat.ops_report = reports.get("ops")
    threat.exec_report = reports.get("executive")
    if threat.ops_report or threat.exec_report:
        threat.status = "reported"
    db.commit()

    return JSONResponse({
        "status": "ok",
        "ops_report": threat.ops_report,
        "exec_report": threat.exec_report,
    })


@router.get("/threats/{threat_id}")
def get_threat(threat_id: str, db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    threat = db.query(ThreatIntel).filter(ThreatIntel.id == uuid.UUID(threat_id)).first()
    if not threat:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({
        "id": str(threat.id),
        "title": threat.title,
        "severity": threat.severity,
        "threat_type": threat.threat_type,
        "cve_ids": threat.cve_ids,
        "confidence": threat.confidence,
        "affected_vendors": threat.affected_vendors,
        "affected_assets": threat.affected_assets_count,
        "ops_report": threat.ops_report,
        "exec_report": threat.exec_report,
        "status": threat.status,
        "source_url": threat.source_url,
        "created_at": threat.created_at.isoformat(),
    })
