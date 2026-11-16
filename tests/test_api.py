
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_profile_routes_are_registered():
    paths = app.openapi()["paths"]

    assert "/api/v1/health/profile/me" in paths
    assert "get" in paths["/api/v1/health/profile/me"]
    assert "put" in paths["/api/v1/health/profile/me"]

    assert "/api/v1/health/profile" in paths
    assert "post" in paths["/api/v1/health/profile"]
