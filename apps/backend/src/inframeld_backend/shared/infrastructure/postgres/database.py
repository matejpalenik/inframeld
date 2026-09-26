"""Own the async PostgreSQL pool, schema compatibility checks, and operation-local sessions."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import URL, Connection, inspect, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from inframeld_backend.shared.infrastructure.postgres.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.postgres.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.postgres.migration_runner import (
    SUPPORTED_SCHEMA_REVISION,
)


class DatabaseStartupError(RuntimeError):
    """Raised when PostgreSQL cannot be reached during startup."""


class DatabaseSchemaCompatibilityError(DatabaseStartupError):
    """Raised when PostgreSQL has an unsupported application schema."""


class Database:
    """Owns PostgreSQL connection resources."""

    def __init__(self, settings: DatabaseSettings) -> None:
        """Configure a lazy connection pool without contacting PostgreSQL."""
        self._target = f"{settings.host}:{settings.port}/{settings.name}"
        self._startup_timeout_seconds = settings.startup_timeout_seconds

        database_url = URL.create(
            drivername="postgresql+psycopg",
            username=settings.user,
            password=settings.password.get_secret_value(),
            host=settings.host,
            port=settings.port,
            database=settings.name,
        )

        self._engine: AsyncEngine = create_async_engine(
            database_url,
            hide_parameters=True,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout_seconds,
            pool_pre_ping=True,
            connect_args={"connect_timeout": settings.connect_timeout_seconds},
        )

        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def _check_schema_compatibility(
        self,
        connection: AsyncConnection,
    ) -> None:
        """Require exactly the supported Alembic revision without creating or modifying schema."""
        version_table = await connection.run_sync(_has_version_table)

        if not version_table:
            raise DatabaseSchemaCompatibilityError(
                f"PostgreSQL schema is not initialized for {self._target}. "
                "Run the operator-controlled migration command."
            )

        result = await connection.execute(select(AlembicVersionRow.version_num))
        revisions = tuple(result.scalars())

        if revisions != (SUPPORTED_SCHEMA_REVISION,):
            observed = ", ".join(str(revision) for revision in revisions) or "none"
            raise DatabaseSchemaCompatibilityError(
                f"Unsupported PostgreSQL schema revision for {self._target}. "
                f"Expected {SUPPORTED_SCHEMA_REVISION!r}; found {observed}."
            )

    async def startup(self) -> None:
        """Verify PostgreSQL availability before serving requests."""

        try:
            async with asyncio.timeout(self._startup_timeout_seconds):
                async with self._engine.connect() as connection:
                    await connection.execute(select(1))
                    await self._check_schema_compatibility(connection)
        except DatabaseSchemaCompatibilityError:
            await self.shutdown()
            raise
        except TimeoutError:
            await self.shutdown()
            raise DatabaseStartupError(
                f"PostgreSQL startup check timed out for {self._target}. "
                "Verify the database host, port, and network access."
            ) from None
        except Exception:
            await self.shutdown()
            raise DatabaseStartupError(
                f"PostgreSQL startup check failed for {self._target}. "
                "Verify the database settings and availability."
            ) from None

    async def shutdown(self) -> None:
        """Dispose all pooled database connections"""
        await self._engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """Create and close one independent database session."""

        async with self._session_factory() as session:
            yield session


def _has_version_table(connection: Connection) -> bool:
    """Inspect schema presence before querying Alembic's revision record."""
    return inspect(connection).has_table("alembic_version", schema="public")
