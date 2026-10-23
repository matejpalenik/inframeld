import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_success_is_committed_before_the_operation_returns(database: Database) -> None:
    organization_id = uuid4()
    async with database.session() as session, SqlAlchemyTransactionManager(session).begin():
        session.add(OrganizationRow(id=organization_id, name="committed"))
    async with database.session() as observer:
        assert await observer.get(OrganizationRow, organization_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_failure_discards_flushed_writes(database: Database, cancelled: bool) -> None:
    """Flushing sends SQL but must not make a failed operation durable."""
    organization_id = uuid4()
    error = asyncio.CancelledError if cancelled else ValueError
    with pytest.raises(error):
        async with database.session() as session:
            async with SqlAlchemyTransactionManager(session).begin():
                session.add(OrganizationRow(id=organization_id, name="rolled back"))
                await session.flush()
                raise error()
    async with database.session() as observer:
        assert await observer.get(OrganizationRow, organization_id) is None


@pytest.mark.asyncio
async def test_existing_transaction_is_rejected_without_ending_it(database: Database) -> None:
    async with database.session() as session, session.begin():
        await session.execute(select(1))
        with pytest.raises(RuntimeError, match="already active"):
            async with SqlAlchemyTransactionManager(session).begin():
                pytest.fail("An existing transaction must not be silently joined.")
        assert session.in_transaction()


@pytest.mark.asyncio
async def test_failure_during_commit_propagates_and_discards_pending_writes(
    database: Database,
) -> None:
    """A constraint error during the final flush cannot become a successful operation."""
    organization_id = uuid4()
    with pytest.raises(IntegrityError):
        async with database.session() as session:
            async with SqlAlchemyTransactionManager(session).begin():
                session.add_all(
                    [
                        OrganizationRow(id=organization_id, name="first"),
                        OrganizationRow(id=organization_id, name="duplicate"),
                    ]
                )
    async with database.session() as observer:
        assert await observer.get(OrganizationRow, organization_id) is None
