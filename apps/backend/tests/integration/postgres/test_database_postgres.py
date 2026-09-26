"""Verify transaction isolation, rollback, constraints, and safe SQL diagnostics."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, String, func, literal, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from tests.support.database_rows import DatabaseTestRow, MissingTestRow

from inframeld_backend.shared.infrastructure.postgres.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


def _create_record_table(session: Session) -> None:
    """Create the test record table through Alembic's schema operations."""
    Operations(MigrationContext.configure(session.connection())).create_table(
        "database_integration",
        Column("id", Integer, primary_key=True),
        Column("label", String, nullable=False, unique=True),
    )


@pytest_asyncio.fixture
async def record_table(database: Database) -> AsyncGenerator[None]:
    """Create a table inside the isolated test database for transaction scenarios."""
    async with database.session() as session, session.begin():
        await session.run_sync(_create_record_table)
    yield


async def test_commit_is_visible_to_a_new_session(database: Database, record_table: None) -> None:
    """Make committed records visible to a later independent read session."""
    async with database.session() as session, session.begin():
        session.add(DatabaseTestRow(id=1, label="committed"))
    async with database.session() as session:
        assert (
            await session.scalar(select(DatabaseTestRow.label).where(DatabaseTestRow.id == 1))
            == "committed"
        )


async def test_exception_rolls_back_the_transaction(database: Database, record_table: None) -> None:
    """Roll back flushed records when the enclosing application operation fails."""
    with pytest.raises(RuntimeError, match="force rollback"):
        async with database.session() as session, session.begin():
            session.add(DatabaseTestRow(id=2, label="rolled-back"))
            await session.flush()
            raise RuntimeError("force rollback")
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DatabaseTestRow)) == 0


async def test_postgresql_enforces_unique_constraints(
    database: Database, record_table: None
) -> None:
    """Reject duplicate labels and roll back all writes in the transaction."""
    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            session.add_all(
                [DatabaseTestRow(id=3, label="duplicate"), DatabaseTestRow(id=4, label="duplicate")]
            )
            await session.flush()
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DatabaseTestRow)) == 0


async def test_sessions_do_not_see_each_others_uncommitted_data(
    database: Database, record_table: None
) -> None:
    """Keep uncommitted records private to the writing transaction."""
    async with database.session() as writer, writer.begin():
        writer.add(DatabaseTestRow(id=5, label="uncommitted"))
        await writer.flush()
        async with database.session() as reader:
            assert await reader.scalar(select(func.count()).select_from(DatabaseTestRow)) == 0


async def test_sql_error_does_not_render_bound_parameter(database: Database) -> None:
    """Hide a real bound value when statement execution fails in the database."""
    private_value = "synthetic-private-sql-value"
    with pytest.raises(DBAPIError) as error:
        async with database.session() as session:
            await session.execute(select(literal(private_value)).select_from(MissingTestRow))
    assert private_value not in str(error.value)
    assert "SQL parameters hidden" in str(error.value)
