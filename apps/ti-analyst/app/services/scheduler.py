"""APScheduler setup for ingestion pipeline job."""
import hashlib
import json
import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.models.models import AgentSettings, AnalysisRun, ThreatIntel

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_ingestion_lock = threading.Lock()       # guards full scheduled pipeline
_source_locks: dict[str, threading.Lock] = {}  # per-source locks for manual poll
_source_locks_mutex = threading.Lock()


def _get_source_lock(source_id: str) -> threading.Lock:
    with _source_locks_mutex:
        if source_id not in _source_locks:
            _source_locks[source_id] = threading.Lock()
        return _source_locks[source_id]


def recover_interrupted_runs() -> int:
    """Mark stale running analysis runs as failed after service restarts."""
    db = SessionLocal()
    try:
        stale_runs = (
            db.query(AnalysisRun)
            .filter(AnalysisRun.status == "running", AnalysisRun.finished_at.is_(None))
            .all()
        )
        if not stale_runs:
            return 0

        finished_at = datetime.now(timezone.utc)
        message = "Interrupted by service restart before completion"
        for run in stale_runs:
            run.status = "failed"
            run.finished_at = finished_at
            run.error_message = f"{run.error_message}; {message}" if run.error_message else message

        db.commit()
        logger.warning("Recovered %d interrupted analysis runs", len(stale_runs))
        return len(stale_runs)
    except Exception:
        db.rollback()
        logger.exception("Failed to recover interrupted analysis runs")
        return 0
    finally:
        db.close()


def _get_model_config(db) -> dict:
    s = db.query(AgentSettings).first()
    if not s:
        return {}
    return {
        "triage_model": s.triage_model,
        "analyst_model": s.analyst_model,
        "infra_model": s.infra_model,
        "triage_prompt": s.triage_prompt,
        "analyst_prompt": s.analyst_prompt,
        "infra_prompt": s.infra_prompt,
        "publisher_ops_prompt": s.publisher_ops_prompt,
        "publisher_exec_prompt": s.publisher_exec_prompt,
    }


def _process_items(items: list[dict], db, graph, os_client, model_config, run) -> tuple[int, int]:
    """Run a list of raw items through the LangGraph pipeline. Returns (processed, critical)."""
    from app.services.notifier import send_telegram_alert

    processed = 0
    critical = 0
    for item in items:
        content = item.get("content", "")
        if not content.strip():
            continue
        dedup_hash = hashlib.sha256(content.encode()).hexdigest()[:64]
        if db.query(ThreatIntel).filter(ThreatIntel.dedup_hash == dedup_hash).first():
            continue

        initial_state = {
            "raw_content": content,
            "metadata": {
                "source_url": item.get("source_url"),
                "source_name": item.get("source_name"),
                "title": item.get("title"),
            },
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
            result = graph.invoke(initial_state)
            if result.get("ignore") or result.get("status") == "error":
                continue

            threat = ThreatIntel(
                source_url=item.get("source_url"),
                source_name=item.get("source_name"),
                raw_content=content[:4000],
                title=result["threat_profile"].get("title") or item.get("title"),
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
            db.commit()
            db.refresh(threat)
            processed += 1

            if threat.severity in ("high", "critical"):
                critical += 1
                send_telegram_alert(
                    f"*[{threat.severity.upper()}] {threat.title}*\n"
                    f"CVEs: {threat.cve_ids or 'N/A'}\n"
                    f"Affected assets: {threat.affected_assets_count}"
                )

            try:
                os_client.index_threat(str(threat.id), {
                    "title": threat.title,
                    "summary": result["threat_profile"].get("summary", ""),
                    "severity": threat.severity,
                    "cve_ids": threat.cve_ids,
                    "created_at": threat.created_at.isoformat(),
                })
            except Exception as idx_err:
                logger.warning("Failed to index threat in OpenSearch: %s", idx_err)

        except Exception:
            logger.exception("Pipeline failed for item from %s", item.get("source_url"))

    return processed, critical


def _run_ingestion_pipeline() -> None:
    from app.graph.workflow import get_graph
    from app.services.ingestion import poll_sources
    from app.services.opensearch_client import OpenSearchClient

    if not _ingestion_lock.acquire(blocking=False):
        logger.warning("Skipping ingestion pipeline: another run is already in progress")
        return

    logger.info("Ingestion pipeline starting")
    db = SessionLocal()
    run = AnalysisRun(trigger="scheduled")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        model_config = _get_model_config(db)
        graph = get_graph()
        os_client = OpenSearchClient()
        items = poll_sources()
        processed, critical = _process_items(items, db, graph, os_client, model_config, run)

        run.finished_at = datetime.now(timezone.utc)
        run.status = "completed"
        run.threats_processed = processed
        run.threats_critical = critical
        db.commit()
        logger.info("Ingestion pipeline done: processed=%d critical=%d", processed, critical)

    except Exception:
        logger.exception("Ingestion pipeline failed")
        run.finished_at = datetime.now(timezone.utc)
        run.status = "failed"
        db.commit()
    finally:
        db.close()
        _ingestion_lock.release()


def run_pipeline_for_source(source_id: str) -> dict:
    """Poll a single source and run its items through the pipeline synchronously."""
    from app.graph.workflow import get_graph
    from app.services.ingestion import poll_source_by_id
    from app.services.opensearch_client import OpenSearchClient

    source_lock = _get_source_lock(source_id)
    if not source_lock.acquire(blocking=False):
        return {"error": "This source is already being polled", "items_fetched": 0, "threats_new": 0}

    db = SessionLocal()
    run = AnalysisRun(trigger="manual_poll")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        model_config = _get_model_config(db)
        graph = get_graph()
        os_client = OpenSearchClient()
        items = poll_source_by_id(source_id)
        processed, critical = _process_items(items, db, graph, os_client, model_config, run)

        run.finished_at = datetime.now(timezone.utc)
        run.status = "completed"
        run.threats_processed = processed
        run.threats_critical = critical
        db.commit()
        logger.info("Single-source poll done: source=%s items=%d threats_new=%d", source_id, len(items), processed)
        return {"items_fetched": len(items), "threats_new": processed}

    except Exception:
        logger.exception("Single-source pipeline failed for source=%s", source_id)
        run.finished_at = datetime.now(timezone.utc)
        run.status = "failed"
        db.commit()
        return {"error": "Pipeline failed", "items_fetched": 0, "threats_new": 0}
    finally:
        db.close()
        source_lock.release()


def _get_settings() -> AgentSettings | None:
    db = SessionLocal()
    try:
        return db.query(AgentSettings).first()
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler

    recover_interrupted_runs()

    agent_settings = _get_settings()
    ingestion_cron = agent_settings.ingestion_cron if agent_settings else settings.ingestion_cron

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_ingestion_pipeline,
        CronTrigger.from_crontab(ingestion_cron),
        id="ingestion_pipeline",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started (ingestion cron: %s)", ingestion_cron)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def trigger_ingestion_now() -> bool:
    """Manually trigger the ingestion pipeline immediately."""
    if _ingestion_lock.locked():
        logger.warning("Manual ingestion trigger ignored: pipeline is already running")
        return False

    threading.Thread(target=_run_ingestion_pipeline, daemon=True, name="ti-analyst-manual").start()
    logger.info("Manual ingestion trigger accepted")
    return True
