from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_continuation_eligibility_dto import (
    JobContinuationEligibilityDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO


class JobRecovery(Protocol):
    """Reassess and retire original work atomically, without dispatching effects."""

    @abstractmethod
    async def recover_in_transaction(
        self, job: JobSnapshotDTO
    ) -> JobContinuationEligibilityDTO: ...
