import uuid
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.models import SchedulerRun
from app.services.scheduler import recover_interrupted_runs


def test_recover_interrupted_runs_marks_running_rows_failed() -> None:
    marker = f"test-recover-{uuid.uuid4().hex[:8]}"

    with SessionLocal() as db:
        stale = SchedulerRun(job_name=marker, status="running")
        done = SchedulerRun(
            job_name=marker,
            status="completed",
            finished_at=datetime.now(timezone.utc),
        )
        db.add_all([stale, done])
        db.commit()
        stale_id = stale.id
        done_id = done.id

    recover_interrupted_runs()

    with SessionLocal() as db:
        stale_row = db.query(SchedulerRun).filter(SchedulerRun.id == stale_id).first()
        done_row = db.query(SchedulerRun).filter(SchedulerRun.id == done_id).first()

        assert stale_row is not None
        assert stale_row.status == "failed"
        assert stale_row.finished_at is not None
        assert stale_row.error_message is not None
        assert "Interrupted by service restart" in stale_row.error_message

        assert done_row is not None
        assert done_row.status == "completed"

        db.query(SchedulerRun).filter(SchedulerRun.id.in_([stale_id, done_id])).delete(synchronize_session=False)
        db.commit()
