"""Unit tests for scheduler logic — DB and graph are mocked."""
import uuid
from unittest.mock import MagicMock, patch


def _make_item(content: str = "CVE-2024-9999 critical vuln") -> dict:
    return {"content": content, "source_url": "https://test.example", "source_name": "test", "title": "Test"}


def _make_graph_result(ignore: bool = False) -> dict:
    if ignore:
        return {
            "ignore": True, "status": "ignored", "threat_profile": {},
            "research_data": None, "affected_assets": [], "reports": {},
            "model_config": {}, "error": None, "raw_content": "",
        }
    return {
        "ignore": False,
        "status": "reported",
        "threat_profile": {
            "title": "Test Threat",
            "threat_type": "rce",
            "cve_ids": ["CVE-2024-9999"],
            "severity": "critical",
            "confidence": "high",
            "affected_vendors": ["TestCorp"],
            "summary": "Critical RCE vulnerability.",
        },
        "research_data": None,
        "affected_assets": [],
        "reports": {"ops": "## Ops", "executive": "Exec summary"},
        "model_config": {},
        "error": None,
        "raw_content": "test content",
    }


@patch("app.services.notifier.send_telegram_alert")
@patch("app.services.scheduler.SessionLocal")
def test_process_items_new_threat(mock_session_local, mock_alert):
    """_process_items should persist a new threat and return (1, 1) for critical severity."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = _make_graph_result(ignore=False)
    mock_os = MagicMock()

    from app.services.scheduler import _process_items
    processed, critical = _process_items(
        [_make_item()], run_id=uuid.uuid4(), graph=mock_graph, os_client=mock_os, model_config={}
    )

    assert processed == 1
    assert critical == 1
    mock_alert.assert_called_once()


@patch("app.services.scheduler.SessionLocal")
def test_process_items_dedup_skips(mock_session_local):
    """_process_items must skip content that already has a matching dedup_hash."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()  # existing hit

    mock_graph = MagicMock()
    mock_os = MagicMock()

    from app.services.scheduler import _process_items
    processed, critical = _process_items(
        [_make_item()], run_id=uuid.uuid4(), graph=mock_graph, os_client=mock_os, model_config={}
    )

    assert processed == 0
    assert critical == 0
    mock_graph.invoke.assert_not_called()


@patch("app.services.scheduler.SessionLocal")
def test_process_items_ignored_content(mock_session_local):
    """_process_items must not persist items the graph marks as ignore=True."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = _make_graph_result(ignore=True)
    mock_os = MagicMock()

    from app.services.scheduler import _process_items
    processed, critical = _process_items(
        [_make_item()], run_id=uuid.uuid4(), graph=mock_graph, os_client=mock_os, model_config={}
    )

    assert processed == 0
    assert critical == 0


@patch("app.services.scheduler.SessionLocal")
def test_process_items_empty_content_skipped(mock_session_local):
    """Items with blank content must be skipped before graph invocation."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_graph = MagicMock()
    mock_os = MagicMock()

    from app.services.scheduler import _process_items
    processed, _ = _process_items(
        [{"content": "   ", "source_url": "https://x.com"}],
        run_id=uuid.uuid4(), graph=mock_graph, os_client=mock_os, model_config={}
    )

    assert processed == 0
    mock_graph.invoke.assert_not_called()


@patch("app.services.scheduler.SessionLocal")
def test_process_items_medium_severity_no_alert(mock_session_local):
    """Non-critical/high threats must not trigger a Telegram alert."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None

    result = _make_graph_result()
    result["threat_profile"]["severity"] = "medium"
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = result
    mock_os = MagicMock()

    with patch("app.services.notifier.send_telegram_alert") as mock_alert:
        from app.services.scheduler import _process_items
        processed, critical = _process_items(
            [_make_item()], run_id=uuid.uuid4(), graph=mock_graph, os_client=mock_os, model_config={}
        )

    assert processed == 1
    assert critical == 0
    mock_alert.assert_not_called()


@patch("app.services.scheduler.SessionLocal")
def test_update_run_status_sets_fields(mock_session_local):
    """_update_run_status must write status, finished_at, and counts."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_run = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_run

    from app.services.scheduler import _update_run_status
    run_id = uuid.uuid4()
    _update_run_status(run_id, "completed", processed=3, critical=1)

    assert mock_run.status == "completed"
    assert mock_run.threats_processed == 3
    assert mock_run.threats_critical == 1
    mock_db.commit.assert_called_once()
