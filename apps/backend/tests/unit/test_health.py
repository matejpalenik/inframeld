import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from inframeld_backend.composition import create_app
from inframeld_backend.main import app
from inframeld_backend.shared.infrastructure.database import DatabaseStartupError
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings, get_settings

client = TestClient(app)


def test_health() -> None:
    """Prove the health endpoint returns the expected healthy response."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_failed_database_startup_prevents_serving_health() -> None:
    """Do not serve HTTP when the database startup check fails."""
    secret = "synthetic-startup-secret"
    unavailable_database = DatabaseSettings(
        host="127.0.0.1",
        port=1,
        name="test",
        user="test",
        password=SecretStr(secret),
        connect_timeout_seconds=1,
        startup_timeout_seconds=0.5,
        pool_timeout_seconds=1,
    )
    settings = get_settings().model_copy(update={"database": unavailable_database})
    application = create_app(settings)

    with pytest.raises(DatabaseStartupError) as failure, TestClient(application) as client:
        client.get("/health")

    assert "PostgreSQL startup check" in str(failure.value)
    assert secret not in str(failure.value)
