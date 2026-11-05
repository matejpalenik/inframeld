from typing import override

from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.shared.application.dtos.job_continuation_eligibility_dto import (
    JobContinuationEligibilityDTO,
)
from inframeld_backend.shared.application.dtos.job_effect_observation_dto import (
    JobEffectObservationDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.job_continuation_disposition import (
    JobContinuationDisposition as Disposition,
)
from inframeld_backend.shared.application.enums.job_effect_observation_kind import (
    JobEffectObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_authorizer import (
    ArtifactCleanupAuthorizer,
)
from inframeld_backend.shared.application.protocols.job_continuation_eligibility import (
    JobContinuationEligibility,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class JobContinuationEligibilityService(JobContinuationEligibility):
    def __init__(
        self,
        jobs: JobStore,
        product: AdmittedWorkAuthorizer,
        cleanup: ArtifactCleanupAuthorizer,
        *,
        supported_payloads: tuple[tuple[str, int], ...],
    ) -> None:
        self._jobs = jobs
        self._product = product
        self._cleanup = cleanup
        self._supported_payloads = supported_payloads

    @override
    async def assess_in_transaction(self, job: JobSnapshotDTO) -> JobContinuationEligibilityDTO:
        authority_changed = False
        complete = False
        try:
            if isinstance(job.binding, ProductJobBindingDTO):
                await self._product.require_current(job.binding.authority)
            else:
                facts = await self._cleanup.require_current(job.job_id, job.binding)
                if facts.binding != job.binding or facts.job_id != job.job_id:
                    raise ConflictError("Cleanup observations changed the original binding.")
                complete = facts.physically_complete
        except AccessDeniedError:
            authority_changed = True
        if job.status is not JobStatus.RUNNING or (
            job.lease_expires_at is not None and job.lease_expires_at > job.observed_at
        ):
            return JobContinuationEligibilityDTO(
                job, Disposition.INELIGIBLE, "current_or_terminal_attempt"
            )

        observation = None
        if job.pending_effect is not None:
            observation = await self._jobs.pending_observation(job)
            if not self._matches(job, observation):
                return JobContinuationEligibilityDTO(
                    job, Disposition.NOT_ESTABLISHED, "unknown_external_effect"
                )
            assert observation is not None
            try:
                await self._jobs.validate_effect_target(observation.binding)
            except ConflictError:
                return JobContinuationEligibilityDTO(
                    job, Disposition.NOT_ESTABLISHED, "artifact_evidence_unavailable"
                )
        reason = None
        if authority_changed:
            reason = "authority_changed"
        elif isinstance(job.binding, ProductJobBindingDTO) and job.cancel_requested:
            reason = "cancellation_requested"
        elif complete:
            reason = "cleanup_already_complete"
        elif job.attempt >= 3:
            reason = "attempt_budget_exhausted"
        elif job.work_deadline is None or job.work_deadline <= job.observed_at:
            reason = "work_deadline_exhausted"
        elif (job.payload.kind, job.payload.version) not in self._supported_payloads:
            reason = "unsupported_payload"
        return JobContinuationEligibilityDTO(
            job,
            Disposition.INELIGIBLE if reason is not None else Disposition.ELIGIBLE,
            reason or "retained_safe_work",
            observation,
        )

    @staticmethod
    def _matches(job: JobSnapshotDTO, observation: JobEffectObservationDTO | None) -> bool:
        if observation is None:
            return False
        binding = observation.binding
        context = binding.context
        return (
            observation.kind is JobEffectObservationKind.NOT_DISPATCHED
            and observation.admitted_at is not None
            and observation.aborted_at is not None
            and observation.admitted_at <= observation.aborted_at <= observation.observed_at
            and observation.consumed_at is None
            and (
                context.job_id,
                context.binding,
                context.payload,
                context.attempt,
                context.fence,
                context.work_deadline,
                context.checkpoint,
                binding.unit,
            )
            == (
                job.job_id,
                job.binding,
                job.payload,
                job.attempt,
                job.fence,
                job.work_deadline,
                job.checkpoint,
                job.pending_effect,
            )
        )
