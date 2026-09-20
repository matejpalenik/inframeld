from logging.config import fileConfig
from typing import cast

from alembic import context
from sqlalchemy import URL, create_engine, pool

from inframeld_backend.shared.infrastructure.migrations import migration_lock
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings, get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def _database_settings() -> DatabaseSettings:
    configured_settings = config.attributes.get("database_settings")

    if configured_settings is not None:
        return cast(DatabaseSettings, configured_settings)

    return get_settings().database


def _database_url(settings: DatabaseSettings) -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )


def run_migrations_offline() -> None:
    raise RuntimeError(
        "Offline migrations are unsupported - use the synchronous online migration command."
    )


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    settings = _database_settings()

    connectable = create_engine(
        _database_url(settings),
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
