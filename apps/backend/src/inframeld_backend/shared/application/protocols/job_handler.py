from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints


class JobHandler(Protocol):
    """Execute one explicitly registered bounded owning workflow outside SQL.

    Saved inputs and checkpoints keep their original meaning. Check current
    source/resource authority in the owning workflow before its protected steps.
    Use checkpoints before effects and a JobOwnership guard in business commits.
    """

    @abstractmethod
    def payload_type(self) -> tuple[str, int]: ...

    @abstractmethod
    async def run(self, context: JobAttemptContextDTO, checkpoints: JobCheckpoints) -> None: ...
