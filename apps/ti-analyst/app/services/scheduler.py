"""APScheduler setup for ingestion pipeline job."""
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone

_PIPELINE_TIMEOUT = 1800  # 30 minutes max per scheduled run
_MAX_ITEMS_PER_RUN = 8    # after batch pretriage only relevant items remain; 8 × ~4 LLM calls × ~60s ≈ 32 min
_PRETRIAGE_BATCH = 25     # items per single batch-pretriage LLM call

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


def _batch_pretriage(candidates: list[tuple[dict, str]], model: str) -> list[tuple[dict, str]]:
    """One LLM call per batch to filter out non-security content before the expensive pipeline.

    Sends up to _PRETRIAGE_BATCH item titles+previews in a single prompt and asks the model
    which indices look security-relevant. Only those pass through to the full LangGraph pipeline.
    Falls back to returning all candidates if the LLM call fails.
    """
    import openai
    from openai import OpenAI

    if not candidates:
        return candidates

    relevant: list[tuple[dict, str]] = []

    for batch_start in range(0, len(candidates), _PRETRIAGE_BATCH):
        batch = candidates[batch_start: batch_start + _PRETRIAGE_BATCH]
        lines = []
        for i, (item, _) in enumerate(batch):
            title = (item.get("title") or "")[:120].replace("\n", " ")
            preview = (item.get("content") or "")[:200].replace("\n", " ")
            lines.append(f"{i}: {title} | {preview}")

        prompt = (
            "You are a cybersecurity relevance filter. "
            "Given the numbered list below, return a JSON object {\"relevant\": [list of indices]} "
            "for items that are about: vulnerabilities, CVEs, exploits, malware, ransomware, "
            "data breaches, network attacks, security patches, or threat intelligence. "
            "Exclude: general tech news, product launches, tutorials, job posts, and "
            "non-security content. Be strict — when in doubt, exclude."
        )
        content = "\n".join(lines)

        try:
            client = OpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content},
                ],
                response_format={"type": "json_object"},
                max_tokens=256,
                timeout=60,
            )
            raw_content = resp.choices[0].message.content
            if not raw_content:
                logger.warning("Batch pretriage: LLM returned empty content for batch offset=%d — including all", batch_start)
                relevant.extend(batch)
                continue
            result = json.loads(raw_content)
            indices = {int(i) for i in result.get("relevant", []) if str(i).isdigit()}
            passed = [batch[i] for i in sorted(indices) if i < len(batch)]
            logger.info(
                "Batch pretriage: %d/%d items passed (batch offset=%d)",
                len(passed), len(batch), batch_start,
            )
            relevant.extend(passed)
        except (openai.APIError, json.JSONDecodeError, Exception) as exc:
            logger.warning("Batch pretriage failed for batch offset=%d: %s — including all", batch_start, exc)
            relevant.extend(batch)

    return relevant


def _process_items(items: list[dict], run_id, graph, os_client, model_config,
                   max_items: int = _MAX_ITEMS_PER_RUN) -> tuple[int, int]:
    """Run a list of raw items through the LangGraph pipeline. Returns (processed, critical).

    Uses its own DB session — safe to run in a worker thread independently of the
    caller's session.

    Batch-deduplication: all dedup hashes are checked in a single IN query before any
    LLM calls are made. If every fetched item is already known the function returns
    immediately without touching the LLM at all.

    At most max_items new items are processed per call to prevent timeouts with slow
    reasoning models.
    """
    from app.services.notifier import send_telegram_alert

    # ── 1. Build candidates (non-empty content) with their dedup hashes ──────────
    # Dedup key: prefer source_url (stable identifier) over content hash so that
    # the same article is never re-processed even if its content is later edited.
    candidates: list[tuple[dict, str]] = []
    for item in items:
        content = item.get("content", "")
        if not content.strip():
            continue
        source_url = (item.get("source_url") or "").strip()
        dedup_input = source_url if source_url else content
        dedup_hash = hashlib.sha256(dedup_input.encode()).hexdigest()[:64]
        candidates.append((item, dedup_hash))

    if not candidates:
        return 0, 0

    # ── 2. Batch-dedup: single IN query, no LLM if nothing is new ────────────────
    db = SessionLocal()
    try:
        all_hashes = [h for _, h in candidates]
        existing = {
            row[0]
            for row in db.query(ThreatIntel.dedup_hash)
            .filter(ThreatIntel.dedup_hash.in_(all_hashes))
            .all()
        }
    finally:
        db.close()

    new_candidates = [(item, h) for item, h in candidates if h not in existing]

    if not new_candidates:
        logger.info(
            "_process_items: all %d items already seen — skipping LLM", len(candidates)
        )
        return 0, 0

    # ── 2b. Batch pre-triage: one cheap LLM call filters out non-security content ─
    triage_model = model_config.get("triage_model", settings.triage_model)
    logger.info("_process_items: batch pretriage of %d new candidates", len(new_candidates))
    new_candidates = _batch_pretriage(new_candidates, triage_model)
    if not new_candidates:
        logger.info("_process_items: all items filtered by pretriage — skipping pipeline")
        return 0, 0

    if len(new_candidates) > max_items:
        logger.info(
            "_process_items: %d new items, capping to max_items=%d (round-robin by source)",
            len(new_candidates), max_items,
        )
        # Round-robin across sources so every source gets a fair chance each run,
        # preventing new sources from being starved by sources with many new items.
        from collections import defaultdict
        by_source: dict[str, list] = defaultdict(list)
        for item, h in new_candidates:
            by_source[item.get("source_name", "")].append((item, h))
        capped: list = []
        source_queues = list(by_source.values())
        idx = 0
        while len(capped) < max_items and any(source_queues):
            q = source_queues[idx % len(source_queues)]
            if q:
                capped.append(q.pop(0))
            idx += 1
        new_candidates = capped

    logger.info(
        "_process_items: %d new item(s) to process (fetched %d, known %d)",
        len(new_candidates), len(candidates), len(existing),
    )

    # ── 3. LLM pipeline — only for genuinely new items ───────────────────────────
    from app.services import progress as _prog
    _prog.update(items_new=len(new_candidates), items_scanned=0, items_processed=0)

    db = SessionLocal()
    processed = 0
    critical = 0
    scanned = 0
    try:
        for item, dedup_hash in new_candidates:
            content = item["content"]
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
                _prog.update(current_source=item.get("source_name", ""), current_agent="ingestor")
                result = graph.invoke(initial_state)
                scanned += 1
                _prog.update(items_scanned=scanned, current_agent="")
                if result.get("ignore"):
                    # Store hash so this item is never re-processed through LLM
                    ignored = ThreatIntel(
                        dedup_hash=dedup_hash,
                        status="ignored",
                        source_name=item.get("source_name"),
                        raw_content=content[:200],
                        analysis_run_id=run_id,
                    )
                    db.add(ignored)
                    db.commit()
                    continue
                if result.get("status") == "error":
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
                    analysis_run_id=run_id,
                )
                db.add(threat)
                db.commit()
                db.refresh(threat)
                processed += 1
                _prog.update(items_processed=processed)

                if threat.severity in ("high", "critical"):
                    critical += 1
                    if threat.affected_assets_count > 0:
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
                logger.exception("Pipeline failed for item from %s run_id=%s", item.get("source_url"), run_id)
    finally:
        db.close()

    return processed, critical


def _update_run_status(run_id, status: str, error_message: str | None = None,
                       processed: int = 0, critical: int = 0) -> None:
    """Write final run status using a fresh session (safe to call from any thread)."""
    db = SessionLocal()
    try:
        run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        if run:
            run.finished_at = datetime.now(timezone.utc)
            run.status = status
            if error_message is not None:
                run.error_message = error_message
            run.threats_processed = processed
            run.threats_critical = critical
            db.commit()
    except Exception:
        logger.exception("Failed to update run status for run_id=%s", run_id)
        db.rollback()
    finally:
        db.close()


def _run_ingestion_pipeline() -> None:
    from app.graph.workflow import get_graph
    from app.services.ingestion import poll_sources
    from app.services.opensearch_client import OpenSearchClient

    if not _ingestion_lock.acquire(blocking=False):
        logger.warning("Skipping ingestion pipeline: another run is already in progress")
        return

    logger.info("Ingestion pipeline starting")

    # Create the run record and close the session immediately — the worker thread
    # uses its own session so there is no shared session across threads.
    run_id = None
    try:
        db = SessionLocal()
        try:
            run = AnalysisRun(trigger="scheduled")
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.id
            model_config = _get_model_config(db)
        finally:
            db.close()
    except Exception:
        logger.exception("Ingestion pipeline failed to create run record")
        _ingestion_lock.release()
        return

    try:
        graph = get_graph()
        os_client = OpenSearchClient()

        # Both poll_sources() and _process_items() run inside the worker thread so
        # the entire pipeline — including Telegram/RSS fetching — is covered by
        # _PIPELINE_TIMEOUT.  Previously poll_sources() ran in the scheduler thread
        # with no timeout, causing indefinite hangs when Telethon's SQLite session
        # lock stalled on sequential multi-source fetches.
        result_holder: dict = {}
        exc_holder: list = []

        def _worker():
            try:
                from app.services import progress as _prog
                _prog.update(active=True, stage="polling", run_id=str(run_id),
                             sources_done=0, sources_total=0, current_source="",
                             items_fetched=0, items_new=0, items_processed=0, current_agent="")

                def _on_source(done, total, current):
                    _prog.update(sources_done=done, sources_total=total, current_source=current)

                items = poll_sources(progress_cb=_on_source)
                _prog.update(stage="processing", items_fetched=len(items))
                result_holder["processed"], result_holder["critical"] = _process_items(
                    items, run_id, graph, os_client, model_config
                )
            except Exception as exc:  # noqa: BLE001
                exc_holder.append(exc)

        worker = threading.Thread(target=_worker, daemon=True, name="ti-analyst-pipeline-worker")
        t0 = time.monotonic()
        worker.start()
        worker.join(timeout=_PIPELINE_TIMEOUT)

        if worker.is_alive():
            elapsed = int(time.monotonic() - t0)
            logger.error("Ingestion pipeline timed out after %ds run_id=%s — marking run as failed", elapsed, run_id)
            _update_run_status(run_id, "failed", f"Pipeline timed out after {elapsed}s")
            return  # lock released in finally; worker thread is orphaned (daemon)

        if exc_holder:
            raise exc_holder[0]

        processed = result_holder.get("processed", 0)
        critical = result_holder.get("critical", 0)
        _update_run_status(run_id, "completed", processed=processed, critical=critical)
        logger.info("Ingestion pipeline done: processed=%d critical=%d", processed, critical)

    except Exception:
        logger.exception("Ingestion pipeline failed")
        _update_run_status(run_id, "failed", "Unexpected pipeline error")
    finally:
        from app.services import progress as _prog
        _prog.clear()
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
        run_id = run.id
    finally:
        db.close()

    try:
        graph = get_graph()
        os_client = OpenSearchClient()
        items = poll_source_by_id(source_id)
        processed, critical = _process_items(items, run_id, graph, os_client, model_config)

        _update_run_status(run_id, "completed", processed=processed, critical=critical)
        logger.info("Single-source poll done: source=%s items=%d threats_new=%d", source_id, len(items), processed)
        return {"items_fetched": len(items), "threats_new": processed}

    except Exception:
        logger.exception("Single-source pipeline failed for source=%s run_id=%s", source_id, run_id)
        _update_run_status(run_id, "failed", "Single-source pipeline error")
        return {"error": "Pipeline failed", "items_fetched": 0, "threats_new": 0}
    finally:
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


def reschedule_ingestion(cron: str) -> None:
    """Apply a new cron expression to the running ingestion job without restart."""
    if not _scheduler or not _scheduler.running:
        logger.warning("reschedule_ingestion called but scheduler is not running")
        return
    _scheduler.reschedule_job(
        "ingestion_pipeline",
        trigger=CronTrigger.from_crontab(cron),
    )
    logger.info("Ingestion pipeline rescheduled to cron: %s", cron)


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
