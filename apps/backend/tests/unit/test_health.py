from fastapi.testclient import TestClient

from inframeld_backend.main import app

client = TestClient(app)


def test_health() -> None:
    """Prove the health endpoint returns the expected healthy response."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
