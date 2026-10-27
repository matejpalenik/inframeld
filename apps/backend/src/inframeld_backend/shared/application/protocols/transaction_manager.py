from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Protocol


class TransactionManager(Protocol):
    """Give one application operation a single atomic database transaction."""

    @abstractmethod
    def begin(self) -> AbstractAsyncContextManager[None]:
        """Open a transaction for an `async with` block and finish it on exit.

        Require a session with no active transaction. Commit after normal block
        completion. If the block raises or is cancelled, roll back and propagate
        the failure. Never join an existing transaction, create a savepoint or
        retry automatically.

        Commit errors also propagate. A lost connection during commit can leave
        its outcome uncertain, so an error alone does not prove rollback.

        Returns:
            An asynchronous context manager that yields no value. Successful
            exit means the transaction committed before the workflow returns.

        Raises:
            RuntimeError: The session already has an active transaction. Leave
                that transaction under its existing owner's control.
        """
        ...
