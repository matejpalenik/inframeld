from abc import abstractmethod
from typing import Protocol


class IdentityRecoveryCleanupReconciler(Protocol):
    """Apply saved complete proof through independent original-release checks."""

    @abstractmethod
    async def reconcile_pending(self, *, limit: int = 25) -> int:
        """Return completed checks from at most twenty-five originals.

        This performs no provider calls. Temporarily unavailable local work is
        deferred, while an ineligible account keeps its block without busy polling.
        """
        ...
