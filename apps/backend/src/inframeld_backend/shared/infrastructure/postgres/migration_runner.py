"""Apply operator-requested Alembic migrations under one bounded PostgreSQL advisory lock."""

import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, Connection, func, select

from inframeld_backend.shared.infrastructure.postgres.database_settings import DatabaseSettings

SUPPORTED_SCHEMA_REVISION = "0001_initial"
MIGRATION_LOCK_KEY = 4_321_017
MIGRATION_LOCK_POLL_INTERVAL_SECONDS = 0.05


BACKEND_ROOT = Path(__file__).resolve().parents[5]
ALEMBIC_CONFIG_PATH = BACKEND_ROOT / "alembic.ini"


class MigrationLockError(RuntimeError):
    """Raised when the PostgreSQL migration lock cannot be acquired."""


@contextmanager
def migration_lock(
    connection: Connection,
    timeout_seconds: float,
) -> Generator[None]:
    """Hold the session-level migration lock until the caller finishes or fails.

    The caller owns the connection. Acquisition commits its implicit read transaction;
    migrations then own their transaction, while the advisory lock remains held.
    Raise MigrationLockError after the configured deadline and always unlock on exit."""
    deadline = time.monotonic() + timeout_seconds

    while True:
        acquired = bool(
            connection.execute(
                select(func.pg_try_advisory_lock(MIGRATION_LOCK_KEY, type_=Boolean())),
            ).scalar_one()
        )

        if acquired:
            # End the implicit transaction created by the SELECT.
            # The session-level advisory lock remains held.
            connection.commit()
            break

        # Each failed SELECT also starts a transaction so we should roll it back here.
        connection.rollback()

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise MigrationLockError(
                "Could not acquire the PostgreSQL migration lock within",
                f"{timeout_seconds:.2f} seconds",
            )

        time.sleep(min(MIGRATION_LOCK_POLL_INTERVAL_SECONDS, remaining))

    try:
        yield
    finally:
        connection.execute(select(func.pg_advisory_unlock(MIGRATION_LOCK_KEY, type_=Boolean())))


def run_migrations(settings: DatabaseSettings) -> None:
    """Apply database migrations to the supported head revision."""
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings

    command.upgrade(config, "head")
