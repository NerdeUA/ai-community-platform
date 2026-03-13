def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ti-analyst"


def test_manifest_returns_name(client):
    response = client.get("/api/v1/manifest")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ti-analyst"
    assert "skills" in data
    assert len(data["skills"]) == 3


def test_manifest_storage_format(client):
    response = client.get("/api/v1/manifest")
    data = response.json()
    storage = data.get("storage", {})
    assert "postgres" in storage
    opensearch = storage.get("opensearch", {})
    assert isinstance(opensearch.get("collections"), list)
    assert len(opensearch["collections"]) > 0


def test_a2a_endpoint_registered(client):
    """A2A endpoint must be registered (any non-404 response)."""
    response = client.post("/api/v1/a2a", json={"skill": "ti.report"})
    assert response.status_code != 404
