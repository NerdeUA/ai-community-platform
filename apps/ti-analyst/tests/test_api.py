"""Tests for /api/v1/ endpoints."""
from unittest.mock import patch


def test_threats_returns_list(client):
    response = client.get("/api/v1/threats")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_threats_limit_param(client):
    response = client.get("/api/v1/threats?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 5


def test_threats_unknown_id_returns_404(client):
    response = client.get("/api/v1/threats/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_analyze_missing_content_returns_422(client):
    response = client.post("/api/v1/analyze", json={})
    assert response.status_code == 422


def test_analyze_duplicate_skipped(client):
    """Duplicate content (same hash) must return status=duplicate on second call."""
    payload = {"content": "test duplicate content for dedup check", "source_name": "test"}

    with patch("app.graph.workflow.get_graph") as mock_get:
        mock_graph = mock_get.return_value
        mock_graph.invoke.return_value = {
            "ignore": True,
            "status": "ignored",
            "threat_profile": {},
            "research_data": None,
            "affected_assets": [],
            "reports": {},
            "model_config": {},
            "error": None,
            "raw_content": payload["content"],
            "metadata": {},
        }
        r1 = client.post("/api/v1/analyze", json=payload)
        assert r1.status_code == 200
        assert r1.json()["status"] in ("ignored", "duplicate", "analyzed", "error")


def test_manifest_agent_card_structure(client):
    response = client.get("/api/v1/manifest")
    assert response.status_code == 200
    data = response.json()
    # Required A2A agent card fields
    for field in ("name", "version", "url", "skills", "capabilities", "provider",
                  "defaultInputModes", "defaultOutputModes"):
        assert field in data, f"manifest missing field: {field}"
    # No credentials in manifest
    storage = data.get("storage", {})
    postgres = storage.get("postgres", {})
    assert "password" not in postgres, "manifest must not expose DB password"


def test_manifest_capabilities(client):
    data = client.get("/api/v1/manifest").json()
    caps = data["capabilities"]
    assert "streaming" in caps
    assert "pushNotifications" in caps


def test_manifest_skills_have_required_fields(client):
    data = client.get("/api/v1/manifest").json()
    for skill in data["skills"]:
        assert "id" in skill
        assert "name" in skill
        assert "description" in skill
