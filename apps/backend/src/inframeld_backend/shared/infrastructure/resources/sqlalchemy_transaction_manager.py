from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class SqlAlchemyTransactionManager(TransactionManager):
    """Wrap the injected SQLAlchemy session's transaction without closing it.

    Bootstrap remains responsible for closing the request-local session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        if self._session.in_transaction():
            raise RuntimeError("A transaction is already active for this operation.")
        async with self._session.begin():
            yield
