from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO


class HumanSuspensionCleanupClaimWriter(Protocol):
    """Claim the next exact original under the shared recovery slot."""

    @abstractmethod
    async def claim_next(
        self, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO | None: ...
