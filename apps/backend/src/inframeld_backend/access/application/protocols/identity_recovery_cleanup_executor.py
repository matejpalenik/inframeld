from abc import abstractmethod
from typing import Protocol


class IdentityRecoveryCleanupExecutor(Protocol):
    """Execute at most one original cleanup attempt outside request handling."""

    @abstractmethod
    async def execute_once(self) -> bool:
        """Return whether work changed, retaining the block until durable completion.

        Claim and checkpoint in bounded transactions, with provider calls between
        them. Cancellation preserves consumed attempts and cannot recall a call.
        """
        ...
