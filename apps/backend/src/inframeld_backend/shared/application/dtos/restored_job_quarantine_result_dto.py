from dataclasses import dataclass
from typing import Self

from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.domain.enums.job_status import JobStatus


@dataclass(frozen=True, slots=True)
class RestoredJobQuarantineResultDTO:
    """Report the reviewed or retained state without revealing private job inputs."""

    status: JobStatus
    attempt: int
    eligible: bool

    @classmethod
    def from_snapshot(cls, job: JobSnapshotDTO) -> Self:
        queued = (
            job.status is JobStatus.QUEUED
            and job.fence is None
            and job.lease_expires_at is None
            and job.pending_effect is None
        )
        expired = (
            job.status is JobStatus.RUNNING
            and job.attempt > 0
            and job.fence is not None
            and job.lease_expires_at is not None
            and job.lease_expires_at <= job.observed_at
        )
        return cls(job.status, job.attempt, queued or expired)
