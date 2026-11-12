from abc import abstractmethod
from typing import Protocol


class HumanSuspensionCleanupExecutor(Protocol):
    """Advance at most one exact suspension cleanup attempt."""

    @abstractmethod
    async def execute_once(self) -> bool:
        """Return whether a suspension attempt was claimed."""
        ...
