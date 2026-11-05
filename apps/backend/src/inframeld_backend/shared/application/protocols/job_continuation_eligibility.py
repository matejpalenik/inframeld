from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_continuation_eligibility_dto import (
    JobContinuationEligibilityDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO


class JobContinuationEligibility(Protocol):
    """Assess retained remaining work in the caller's coordinated transaction.

    Open no transaction and perform no provider I/O. The caller retains owner,
    queue and job coordination through any checked recovery transition.
    """

    @abstractmethod
    async def assess_in_transaction(self, job: JobSnapshotDTO) -> JobContinuationEligibilityDTO: ...
