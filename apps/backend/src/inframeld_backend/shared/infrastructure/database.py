import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from inframeld_backend.shared.infrastructure.migrations import SUPPORTED_SCHEMA_REVISION
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings


class DatabaseStartupError(RuntimeError):
    """Raised when PostgreSQL cannot be reached during startup."""


class DatabaseSchemaCompatibilityError(DatabaseStartupError):
    """Raised when PostgreSQL has an unsupported application schema."""


class Database:
    """Owns PostgreSQL connection resources."""

    def __init__(self, settings: DatabaseSettings) -> None:
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
        version_table = await connection.scalar(
            text("SELECT to_regclass('public.alembic_version')")
        )

        if version_table is None:
            raise DatabaseSchemaCompatibilityError(
                f"PostgreSQL schema is not initialized for {self._target}. "
                "Run the operator-controlled migration command."
            )

        result = await connection.execute(text("SELECT version_num FROM public.alembic_version"))
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
                    await connection.execute(text("SELECT 1"))
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
