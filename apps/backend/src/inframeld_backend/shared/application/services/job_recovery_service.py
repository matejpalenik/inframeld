from datetime import timedelta
from typing import override

from inframeld_backend.shared.application.dtos.job_continuation_eligibility_dto import (
    JobContinuationEligibilityDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.enums.job_continuation_disposition import (
    JobContinuationDisposition,
)
from inframeld_backend.shared.application.protocols.job_continuation_eligibility import (
    JobContinuationEligibility,
)
from inframeld_backend.shared.application.protocols.job_recovery import JobRecovery
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class JobRecoveryService(JobRecovery):
    def __init__(self, jobs: JobStore, eligibility: JobContinuationEligibility) -> None:
        self._jobs = jobs
        self._eligibility = eligibility

    @override
    async def recover_in_transaction(self, job: JobSnapshotDTO) -> JobContinuationEligibilityDTO:
        result = await self._eligibility.assess_in_transaction(job)
        if result.job != job:
            raise RuntimeError("Recovery assessment returned another original attempt.")
        if job.status is not JobStatus.RUNNING or (
            job.lease_expires_at is not None and job.lease_expires_at > job.observed_at
        ):
            return result
        if result.disposition is JobContinuationDisposition.NOT_ESTABLISHED:
            status = JobStatus.RECOVERY_REQUIRED
        else:
            if result.observation is not None:
                await self._jobs.consume_effect(job, result.observation)
            status = (
                JobStatus.QUEUED
                if result.disposition is JobContinuationDisposition.ELIGIBLE
                else JobStatus.CANCELED
                if result.reason == "cancellation_requested"
                else JobStatus.SUCCEEDED
                if result.reason == "cleanup_already_complete"
                else JobStatus.FAILED
            )
        await self._jobs.retire_attempt(
            job,
            status=status,
            reason=result.reason,
            due_at=job.observed_at + timedelta(seconds=min(5 * job.attempt, 15)),
        )
        return result
