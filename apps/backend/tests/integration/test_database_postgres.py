import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from inframeld_backend.shared.infrastructure.database import Database
from inframeld_backend.shared.infrastructure.settings import get_settings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture
async def database() -> AsyncGenerator[Database]:
    database = Database(get_settings().database)
    await database.startup()

    try:
        yield database
    finally:
        await database.shutdown()


@pytest_asyncio.fixture
async def table_name(database: Database) -> AsyncGenerator[str]:
    name = f"database_integration_{uuid4().hex}"

    async with database.session() as session, session.begin():
        await session.execute(
            text(
                f"""CREATE TABLE "{name}" ( id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE ) """
            )
        )

    try:
        yield name
    finally:
        async with database.session() as session, session.begin():
            await session.execute(text(f'DROP TABLE IF EXISTS "{name}"'))


async def test_commit_is_visible_to_a_new_session(database: Database, table_name: str) -> None:
    """Prove committed data is visible from a separate database session."""

    async with database.session() as session, session.begin():
        await session.execute(
            text(f'INSERT INTO "{table_name}" (id, label) VALUES (:id, :label)'),
            {"id": 1, "label": "committed"},
        )

    async with database.session() as session:
        result = await session.execute(
            text(f'SELECT label FROM "{table_name}" WHERE id = :id'), {"id": 1}
        )

    assert result.scalar_one() == "committed"


async def test_exception_rolls_back_the_transaction(database: Database, table_name: str) -> None:
    """Prove an exception rolls back the whole explicit transaction."""

    with pytest.raises(RuntimeError, match="force rollback"):
        async with database.session() as session, session.begin():
            await session.execute(
                text(f'INSERT INTO "{table_name}" (id, label) VALUES (:id, :label)'),
                {"id": 2, "label": "rolled-back"},
            )
            raise RuntimeError("force rollback")

    async with database.session() as session:
        result = await session.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}" WHERE id = :id'), {"id": 2}
        )

    assert result.scalar_one() == 0


async def test_postgresql_enforces_unique_constraints(database: Database, table_name: str) -> None:
    """Prove PostgreSQL rejects duplicate values and rolls back the transaction."""

    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            await session.execute(
                text(f'INSERT INTO "{table_name}" (id, label) VALUES (:id, :label)'),
                {"id": 3, "label": "duplicate"},
            )

            await session.execute(
                text(f'INSERT INTO "{table_name}" (id, label) VALUES (:id, :label)'),
                {"id": 4, "label": "duplicate"},
            )

    async with database.session() as session:
        result = await session.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))

    assert result.scalar_one() == 0


async def test_sessions_do_not_see_each_others_uncommitted_data(
    database: Database, table_name: str
) -> None:
    """Prove one session cannot read another session's uncommitted data."""

    async with database.session() as writer, writer.begin():
        await writer.execute(
            text(f'INSERT INTO "{table_name}" (id, label) VALUES (:id, :label)'),
            {"id": 5, "label": "uncommitted"},
        )

        async with database.session() as reader:
            result = await reader.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}" WHERE id = :id'), {"id": 5}
            )

        assert result.scalar_one() == 0
