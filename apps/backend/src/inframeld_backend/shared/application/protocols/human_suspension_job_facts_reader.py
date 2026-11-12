from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.shared.application.dtos.human_suspension_job_facts_dto import (
    HumanSuspensionJobFactsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO


class HumanSuspensionJobFactsReader(Protocol):
    @abstractmethod
    async def read_live_attempt(
        self, context: JobAttemptContextDTO, *, worker_id: UUID
    ) -> HumanSuspensionJobFactsDTO | None:
        """Observe exact current backing and attempt in the caller transaction."""
        ...
