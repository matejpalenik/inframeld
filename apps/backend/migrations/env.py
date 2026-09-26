"""Run authoritative Alembic migrations online using validated settings and a migration lock."""

from logging.config import fileConfig
from typing import cast

from alembic import context
from sqlalchemy import URL, create_engine, pool

from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.migrations.migration_runner import migration_lock
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The historical migrations own DDL. Partial read mappings are not an
# authoritative autogeneration model of all constraints and tables.
target_metadata = None


def _database_settings() -> DatabaseSettings:
    """Use the migration command's injected settings or load the process configuration."""
    # Alembic attributes are an untyped framework boundary.
    configured_settings = cast(object, config.attributes.get("database_settings"))

    if isinstance(configured_settings, DatabaseSettings):
        return configured_settings
    if configured_settings is not None:
        raise TypeError("Migration database settings must be validated DatabaseSettings.")

    return get_settings().database


def _database_url(settings: DatabaseSettings) -> URL:
    """Convert validated database settings into a driver URL without rendering its password."""
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )


def run_migrations_offline() -> None:
    """Reject offline migration execution because the lock and transaction require PostgreSQL."""
    raise RuntimeError(
        "Offline migrations are unsupported - use the synchronous online migration command."
    )


def run_migrations_online() -> None:
    """Own a synchronous engine, hold the migration lock, and apply DDL in one transaction."""

    settings = _database_settings()

    connectable = create_engine(
        _database_url(settings),
        hide_parameters=True,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": settings.connect_timeout_seconds},
    )

    try:
        with (
            connectable.connect() as connection,
            migration_lock(connection, settings.migration_lock_timeout_seconds),
        ):
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
