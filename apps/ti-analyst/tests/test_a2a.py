"""Tests for POST /api/v1/a2a endpoint."""
from unittest.mock import patch


def test_a2a_unknown_skill_returns_400(client):
    response = client.post("/api/v1/a2a", json={"skill": "unknown.skill"})
    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "Unknown skill" in data["error"]


def test_a2a_response_has_request_id(client):
    response = client.post("/api/v1/a2a", json={"skill": "ti.report"})
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert data["request_id"]


def test_a2a_request_id_echoed(client):
    response = client.post(
        "/api/v1/a2a",
        json={"skill": "ti.report", "request_id": "test-req-id-123"},
    )
    assert response.status_code == 200
    assert response.json()["request_id"] == "test-req-id-123"


def test_a2a_ti_report_returns_threats_list(client):
    response = client.post("/api/v1/a2a", json={"skill": "ti.report", "params": {"limit": 5}})
    assert response.status_code == 200
    data = response.json()
    assert data["skill"] == "ti.report"
    assert data["status"] == "ok"
    assert "threats" in data["result"]
    assert isinstance(data["result"]["threats"], list)


def test_a2a_ti_inventory_returns_assets(client):
    response = client.post("/api/v1/a2a", json={"skill": "ti.inventory", "params": {"limit": 10}})
    assert response.status_code == 200
    data = response.json()
    assert data["skill"] == "ti.inventory"
    assert data["status"] == "ok"
    assert "assets" in data["result"]
    assert isinstance(data["result"]["assets"], list)


def test_a2a_ti_analyze_missing_content_returns_400(client):
    response = client.post("/api/v1/a2a", json={"skill": "ti.analyze", "params": {}})
    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "content" in data["error"]


def test_a2a_ti_analyze_invokes_graph(client):
    skill_result = {
        "status": "analyzed",
        "threat_id": "00000000-0000-0000-0000-000000000001",
        "severity": "critical",
        "title": "nginx RCE",
        "affected_assets": 0,
    }
    # Patch directly inside _SKILL_MAP so the already-bound dict entry is replaced
    import app.routers.api.a2a as a2a_mod
    original = a2a_mod._SKILL_MAP["ti.analyze"]
    try:
        a2a_mod._SKILL_MAP["ti.analyze"] = lambda params, db: skill_result
        response = client.post(
            "/api/v1/a2a",
            json={
                "skill": "ti.analyze",
                "params": {"content": "CVE-2024-5678 critical RCE in nginx"},
                "request_id": "a2a-test-123",
            },
        )
    finally:
        a2a_mod._SKILL_MAP["ti.analyze"] = original

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["request_id"] == "a2a-test-123"
    assert data["result"]["severity"] == "critical"


def test_a2a_ti_inventory_vendor_filter(client):
    response = client.post(
        "/api/v1/a2a",
        json={"skill": "ti.inventory", "params": {"vendor": "cisco", "limit": 5}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "assets" in data["result"]


def test_a2a_ti_report_severity_filter(client):
    response = client.post(
        "/api/v1/a2a",
        json={"skill": "ti.report", "params": {"severity": "critical", "limit": 10}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # All returned threats (if any) must match the requested severity
    for threat in data["result"]["threats"]:
        assert threat["severity"] == "critical"
