from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)

_AVAILABILITY_ERRORS = (OperationalError, InterfaceError, SqlAlchemyTimeoutError)


class SqlAlchemyRecoveryTransactionManager(TransactionManager):
    """Keep temporary storage failures recoverable within a recovery operation.

    Preserve the caller's cancellation or unrelated failure if rollback also
    fails. Discard operation-local resources after failure. An unavailable
    commit acknowledgment does not prove rollback.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._transactions = SqlAlchemyTransactionManager(session)

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        body_failure: BaseException | None = None
        try:
            async with self._transactions.begin():
                try:
                    yield
                except BaseException as error:
                    body_failure = error
                    raise
        except _AVAILABILITY_ERRORS:
            if body_failure is not None and not isinstance(body_failure, _AVAILABILITY_ERRORS):
                raise body_failure from body_failure.__cause__

            raise DependencyUnavailableError(
                "Recovery database is temporarily unavailable."
            ) from None
