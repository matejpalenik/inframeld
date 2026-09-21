from time import perf_counter

import pytest
from pydantic import SecretStr

from inframeld_backend.shared.infrastructure.database import Database, DatabaseStartupError
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.timing import elapsed_milliseconds


@pytest.mark.asyncio
async def test_startup_failure_is_bounded_and_secret_safe() -> None:
    """Prove database startup fails quickly without exposing connection secrets."""

    settings = DatabaseSettings(
        host="127.0.0.1",
        port=1,
        name="test",
        user="test",
        password=SecretStr("test-secret"),
        connect_timeout_seconds=1,
        startup_timeout_seconds=0.5,
        pool_timeout_seconds=1,
    )

    database = Database(settings)

    started_at = perf_counter()

    try:
        with pytest.raises(DatabaseStartupError) as error:
            await database.startup()
    finally:
        await database.shutdown()

    elapsed = elapsed_milliseconds(started_at)

    assert elapsed < 2_000
    assert "test-secret" not in str(error.value)
    assert "PostgreSQL startup check" in str(error.value)
