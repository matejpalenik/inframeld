import asyncio
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
    SqlAlchemyRecoveryTransactionManager,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["entry", "work", "commit", "rollback"])
@pytest.mark.parametrize(
    "failure",
    [
        OperationalError("private-statement", None, ConnectionError("private-driver-message")),
        InterfaceError("private-statement", None, ConnectionError("private-driver-message")),
        SqlAlchemyTimeoutError("private-pool-message"),
    ],
    ids=["connection", "interface", "pool"],
)
async def test_database_availability_failure_is_safe_and_never_retried(
    stage: Literal["entry", "work", "commit", "rollback"], failure: Exception
) -> None:
    entries = 0

    # Control transaction entry/exit without needing a database for error translation.
    @asynccontextmanager
    async def interrupted_transaction(
        _manager: SqlAlchemyTransactionManager,
    ) -> AsyncGenerator[None]:
        nonlocal entries
        entries += 1
        if stage == "entry":
            raise failure

        try:
            yield
        except BaseException:
            if stage == "rollback":
                raise failure from None
            raise

        if stage == "commit":
            raise failure

    async with AsyncSession() as session:
        manager = SqlAlchemyRecoveryTransactionManager(session)
        with (
            patch.object(SqlAlchemyTransactionManager, "begin", interrupted_transaction),
            pytest.raises(DependencyUnavailableError) as caught,
        ):
            async with manager.begin():
                if stage == "work":
                    raise failure
                if stage == "rollback":
                    raise OperationalError(
                        "private-original", None, ConnectionError("Unavailable.")
                    )

    assert entries == 1
    rendered = "".join(traceback.format_exception(caught.value))
    assert "private-" not in rendered
    assert "private-" not in repr(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback_unavailable", [False, True])
@pytest.mark.parametrize(
    "failure",
    [
        asyncio.CancelledError(),
        ConflictError(),
        IntegrityError("statement", None, ValueError("constraint violation")),
        RuntimeError("Programming failure."),
    ],
    ids=["cancellation", "conflict", "integrity", "programming"],
)
async def test_unrelated_failures_propagate_unchanged(
    failure: BaseException, rollback_unavailable: bool
) -> None:
    original_begin = SqlAlchemyTransactionManager.begin
    original_cause = (
        ValueError("Original domain rejection.") if isinstance(failure, ConflictError) else None
    )
    failure.__cause__ = original_cause

    @asynccontextmanager
    async def finish_transaction(manager: SqlAlchemyTransactionManager) -> AsyncGenerator[None]:
        async with original_begin(manager):
            try:
                yield
            except BaseException:
                if rollback_unavailable:
                    raise OperationalError(
                        "rollback", None, ConnectionError("Unavailable.")
                    ) from None
                raise

    async with AsyncSession() as session:
        with (
            patch.object(SqlAlchemyTransactionManager, "begin", finish_transaction),
            pytest.raises(type(failure)) as caught,
        ):
            async with SqlAlchemyRecoveryTransactionManager(session).begin():
                raise failure

        assert caught.value is failure
        assert caught.value.__cause__ is original_cause
        assert not session.in_transaction()


@pytest.mark.asyncio
async def test_an_existing_transaction_is_left_under_its_owners_control() -> None:
    async with AsyncSession() as session, session.begin():
        with pytest.raises(RuntimeError, match="already active"):
            async with SqlAlchemyRecoveryTransactionManager(session).begin():
                pytest.fail("An existing transaction cannot be joined.")

        assert session.in_transaction()
