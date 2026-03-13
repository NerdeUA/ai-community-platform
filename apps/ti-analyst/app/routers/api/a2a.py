"""A2A (Agent-to-Agent) endpoint for ti-analyst.

Supports skills declared in /api/v1/manifest:
  ti.analyze   — run the LangGraph threat analysis pipeline on provided content
  ti.inventory — query the monitored asset inventory
  ti.report    — retrieve recent processed threat intelligence
"""
import hashlib
import json
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AgentSettings, AnalysisRun, Asset, ThreatIntel

router = APIRouter(prefix="/api/v1", tags=["a2a"])
logger = logging.getLogger(__name__)


# ── Envelope ────────────────────────────────────────────────────────────────

class A2AParams(BaseModel):
    content: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    severity: str | None = None
    vendor: str | None = None
    limit: int = 20


class A2ARequest(BaseModel):
    skill: str
    params: A2AParams = A2AParams()
    request_id: str | None = None
    trace_id: str | None = None
    conversation_id: str | None = None
    agent_run_id: str | None = None
    parent_agent_run_id: str | None = None
    hop: int = 0


class A2AResponse(BaseModel):
    request_id: str
    skill: str
    status: str
    result: dict[str, Any] = {}
    error: str | None = None


# ── Skill: ti.analyze ───────────────────────────────────────────────────────

def _skill_analyze(params: A2AParams, db: Session) -> dict[str, Any]:
    if not params.content:
        return {"error": "params.content is required for ti.analyze"}

    dedup_hash = hashlib.sha256(params.content.encode()).hexdigest()[:64]
    existing = db.query(ThreatIntel).filter(ThreatIntel.dedup_hash == dedup_hash).first()
    if existing:
        return {"status": "duplicate", "threat_id": str(existing.id)}

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

    run = AnalysisRun(trigger="a2a")
    db.add(run)
    db.commit()
    db.refresh(run)

    initial_state = {
        "raw_content": params.content,
        "metadata": {"source_url": params.source_url, "source_name": params.source_name},
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
        from app.graph.workflow import get_graph
        result = get_graph().invoke(initial_state)
    except Exception as exc:
        run.status = "error"
        run.error_message = str(exc)
        db.commit()
        logger.error("A2A ti.analyze pipeline failed: %s", exc)
        return {"error": str(exc)}

    if result.get("ignore"):
        run.status = "ignored"
        db.commit()
        return {"status": "ignored", "reason": "content not threat-relevant"}

    threat = ThreatIntel(
        source_url=params.source_url,
        source_name=params.source_name,
        raw_content=params.content[:4000],
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
        from app.services.opensearch_client import OpenSearchClient
        OpenSearchClient().index_threat(str(threat.id), {
            "title": threat.title,
            "summary": result["threat_profile"].get("summary", ""),
            "severity": threat.severity,
            "cve_ids": threat.cve_ids,
        })
    except Exception as idx_err:
        logger.warning("A2A ti.analyze: OpenSearch index failed: %s", idx_err)

    return {
        "status": "analyzed",
        "threat_id": str(threat.id),
        "severity": threat.severity,
        "title": threat.title,
        "affected_assets": threat.affected_assets_count,
    }


# ── Skill: ti.inventory ─────────────────────────────────────────────────────

def _skill_inventory(params: A2AParams, db: Session) -> dict[str, Any]:
    q = db.query(Asset)
    if params.vendor:
        q = q.filter(Asset.vendor.ilike(f"%{params.vendor}%"))
    assets = q.order_by(Asset.criticality.desc()).limit(params.limit).all()
    return {
        "total": len(assets),
        "assets": [
            {
                "id": str(a.id),
                "name": a.name,
                "vendor": a.vendor,
                "model": a.model,
                "criticality": a.criticality,
                "software_version": a.software_version,
            }
            for a in assets
        ],
    }


# ── Skill: ti.report ────────────────────────────────────────────────────────

def _skill_report(params: A2AParams, db: Session) -> dict[str, Any]:
    q = db.query(ThreatIntel)
    if params.severity:
        q = q.filter(ThreatIntel.severity == params.severity)
    threats = q.order_by(ThreatIntel.created_at.desc()).limit(params.limit).all()
    return {
        "total": len(threats),
        "threats": [
            {
                "id": str(t.id),
                "title": t.title,
                "severity": t.severity,
                "threat_type": t.threat_type,
                "cve_ids": t.cve_ids,
                "ops_report": t.ops_report,
                "exec_report": t.exec_report,
                "created_at": t.created_at.isoformat(),
            }
            for t in threats
        ],
    }


_SKILL_MAP = {
    "ti.analyze": _skill_analyze,
    "ti.inventory": _skill_inventory,
    "ti.report": _skill_report,
}


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/a2a")
def handle_a2a(req: A2ARequest, db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """Dispatch an A2A request to the matching skill."""
    response_request_id = req.request_id or str(uuid.uuid4())

    handler = _SKILL_MAP.get(req.skill)
    if handler is None:
        return JSONResponse(
            A2AResponse(
                request_id=response_request_id,
                skill=req.skill,
                status="error",
                error=f"Unknown skill: {req.skill!r}. Available: {list(_SKILL_MAP)}",
            ).model_dump(),
            status_code=400,
        )

    try:
        result = handler(req.params, db)
    except Exception as exc:
        logger.error("A2A skill=%s failed: %s", req.skill, exc)
        return JSONResponse(
            A2AResponse(
                request_id=response_request_id,
                skill=req.skill,
                status="error",
                error=str(exc),
            ).model_dump(),
            status_code=500,
        )

    if "error" in result and len(result) == 1:
        return JSONResponse(
            A2AResponse(
                request_id=response_request_id,
                skill=req.skill,
                status="error",
                error=result["error"],
            ).model_dump(),
            status_code=400,
        )

    return JSONResponse(
        A2AResponse(
            request_id=response_request_id,
            skill=req.skill,
            status="ok",
            result=result,
        ).model_dump()
    )
