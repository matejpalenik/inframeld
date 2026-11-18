from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class RetainedHistorySafetyHeadroom(Protocol):
    """Apply the independently owned safety-space gate during ordinary admission."""

    @abstractmethod
    async def require_headroom(self, *, installation_id: InstallationId) -> None:
        """Reject missing, stale or unsafe evidence without performing external I/O.

        Use already verified short-lived evidence or current local SQL facts.
        Ordinary history does not spend the safety and emergency reserves.
        """
        ...
