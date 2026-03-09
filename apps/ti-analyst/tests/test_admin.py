"""Tests for admin UI endpoints."""
import uuid


def test_sources_page_returns_html(client):
    response = client.get("/admin/sources")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_assets_page_returns_html(client):
    response = client.get("/admin/assets")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_settings_page_returns_html(client):
    response = client.get("/admin/settings")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_dashboard_returns_html(client):
    response = client.get("/web/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_create_source_invalid_url_returns_400(client):
    response = client.post(
        "/admin/sources/create",
        data={"name": "Bad Source", "source_type": "rss", "url": "not-a-url", "poll_interval_minutes": "60"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_create_source_valid_rss(client):
    unique_name = f"Test RSS {uuid.uuid4().hex[:8]}"
    response = client.post(
        "/admin/sources/create",
        data={
            "name": unique_name,
            "source_type": "rss",
            "url": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
            "poll_interval_minutes": "60",
        },
        follow_redirects=False,
    )
    # Successful create redirects to /admin/sources
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/sources"


def test_create_telegram_source_without_resolve_returns_400(client):
    response = client.post(
        "/admin/sources/create",
        data={
            "name": "My Channel",
            "source_type": "telegram",
            "url": "",
            "poll_interval_minutes": "60",
            "telegram_id": "0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_resolve_telegram_empty_input(client):
    response = client.post(
        "/admin/sources/resolve-telegram",
        json={"channel_input": ""},
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_resolve_telegram_no_token(client):
    """When bot token is not configured, resolver returns 422."""
    from unittest.mock import patch
    with patch("app.config.settings.telegram_bot_token", ""):
        response = client.post(
            "/admin/sources/resolve-telegram",
            json={"channel_input": "@telegram"},
        )
    assert response.status_code == 422
    assert "error" in response.json()


def test_delete_nonexistent_source_redirects(client):
    response = client.post(
        "/admin/sources/00000000-0000-0000-0000-000000000000/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_poll_nonexistent_source_returns_404(client):
    response = client.post("/admin/sources/00000000-0000-0000-0000-000000000000/poll")
    assert response.status_code == 404
    assert "error" in response.json()


def test_poll_source_returns_result(client):
    """Polling a real source runs the pipeline and returns items_fetched/threats_new."""
    from unittest.mock import patch

    unique_name = f"Poll Test {uuid.uuid4().hex[:8]}"
    # Create a source first
    client.post(
        "/admin/sources/create",
        data={
            "name": unique_name,
            "source_type": "rss",
            "url": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
            "poll_interval_minutes": "60",
        },
        follow_redirects=False,
    )
    # Get the source id
    from app.database import SessionLocal
    from app.models.models import ThreatSource
    db = SessionLocal()
    source = db.query(ThreatSource).filter(ThreatSource.name == unique_name).first()
    db.close()
    assert source is not None

    with patch("app.services.scheduler.run_pipeline_for_source") as mock_run:
        mock_run.return_value = {"items_fetched": 5, "threats_new": 1}
        response = client.post(f"/admin/sources/{source.id}/poll")

    assert response.status_code == 200
    data = response.json()
    assert "items_fetched" in data
    assert "threats_new" in data


def test_update_source_name(client):
    unique_name = f"Update Test {uuid.uuid4().hex[:8]}"
    client.post(
        "/admin/sources/create",
        data={
            "name": unique_name,
            "source_type": "rss",
            "url": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
            "poll_interval_minutes": "60",
        },
        follow_redirects=False,
    )
    from app.database import SessionLocal
    from app.models.models import ThreatSource
    db = SessionLocal()
    source = db.query(ThreatSource).filter(ThreatSource.name == unique_name).first()
    db.close()
    assert source is not None

    new_name = f"Updated {uuid.uuid4().hex[:8]}"
    response = client.post(
        f"/admin/sources/{source.id}/update",
        data={"name": new_name, "url": source.url, "poll_interval_minutes": "30"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    updated = db.query(ThreatSource).filter(ThreatSource.id == source.id).first()
    db.close()
    assert updated.name == new_name
    assert updated.poll_interval_minutes == 30


def test_update_source_invalid_url_returns_400(client):
    unique_name = f"Bad URL Test {uuid.uuid4().hex[:8]}"
    client.post(
        "/admin/sources/create",
        data={
            "name": unique_name,
            "source_type": "rss",
            "url": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
            "poll_interval_minutes": "60",
        },
        follow_redirects=False,
    )
    from app.database import SessionLocal
    from app.models.models import ThreatSource
    db = SessionLocal()
    source = db.query(ThreatSource).filter(ThreatSource.name == unique_name).first()
    db.close()

    response = client.post(
        f"/admin/sources/{source.id}/update",
        data={"name": unique_name, "url": "not-a-url", "poll_interval_minutes": "60"},
        follow_redirects=False,
    )
    assert response.status_code == 400
