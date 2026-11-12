from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.shared.application.dtos.human_suspension_job_facts_dto import (
    HumanSuspensionJobFactsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO


class HumanSuspensionJobAuthorizer(Protocol):
    @abstractmethod
    async def require_current(
        self, context: JobAttemptContextDTO, *, worker_id: UUID
    ) -> HumanSuspensionJobFactsDTO:
        """Require an exact live cleanup attempt in the caller's transaction.

        The observation grants no provider dispatch or authority to release recovery.
        """
        ...
