"""Control job observations for service tests, without claiming persistent proof."""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_cleanup_facts_dto import (
    ArtifactCleanupFactsDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.dtos.job_effect_observation_dto import (
    JobEffectObservationDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.enums.job_effect_observation_kind import (
    JobEffectObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.application.protocols.artifact_cleanup_authorizer import (
    ArtifactCleanupAuthorizer,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def original_effect() -> JobEffectBindingDTO:
    now = datetime.now(UTC)
    scope = ArtifactScopeDTO(
        InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
    )
    target = ArtifactAttemptId(UUID(int=4))
    binding = ArtifactCleanupJobBindingDTO(
        ArtifactCleanupObligationId(UUID(int=5)),
        scope,
        ArtifactCleanupKind.ABANDONED_STAGING,
        UnadmittedStagingArtifactOriginDTO(target, RequestId(UUID(int=6))),
    )
    context = JobAttemptContextDTO(
        JobId(UUID(int=7)),
        binding,
        JobPayload("artifact.cleanup", 1, b"original"),
        1,
        JobFence(UUID(int=8)),
        now + timedelta(minutes=2),
        b"checkpoint",
    )
    return JobEffectBindingDTO(
        JobEffectId(UUID(int=9)),
        context,
        "delete-original",
        JobEffectAction.DELETE,
        ArtifactId(UUID(int=10)),
        target,
        scope,
        None,
        None,
    )


class MockEffectStore(JobStore):
    """Observe unit decisions only. PostgreSQL must separately prove atomicity."""

    def __init__(self, binding: JobEffectBindingDTO) -> None:
        self.binding = binding
        now = datetime.now(UTC)
        context = binding.context
        self.job = JobSnapshotDTO(
            context.job_id,
            context.binding,
            context.payload,
            JobStatus.RUNNING,
            now,
            now + timedelta(hours=1),
            now,
            now,
            context.attempt,
            context.work_deadline,
            context.fence,
            now + timedelta(seconds=30),
            False,
            binding.unit,
            None,
            context.checkpoint,
        )
        self.observation: JobEffectObservationDTO | None = JobEffectObservationDTO(binding, now)
        self.events: list[str] = []
        self.target_error = False
        self.fence_error = False

    @override
    async def register_effect(self, binding: JobEffectBindingDTO) -> None:
        self.events.append("register")
        self.observation = JobEffectObservationDTO(binding, self.job.observed_at)

    @override
    async def effect(self, effect_id: JobEffectId) -> JobEffectObservationDTO | None:
        self.events.append("effect")
        return self.observation if effect_id == self.binding.effect_id else None

    @override
    async def validate_effect_target(self, binding: JobEffectBindingDTO) -> None:
        self.events.append("target")
        if self.target_error or binding != self.binding:
            raise ConflictError("The original artifact target changed.")

    @override
    async def admit_effect(self, observation: JobEffectObservationDTO) -> None:
        self.events.append("admit")
        if self.observation is None or self.observation.admitted_at is not None:
            raise ConflictError("The physical invocation was already admitted.")
        self.observation = replace(observation, admitted_at=observation.observed_at)

    @override
    async def record_effect_abort(self, observation: JobEffectObservationDTO) -> None:
        self.events.append("abort")
        self.observation = replace(
            observation,
            kind=JobEffectObservationKind.NOT_DISPATCHED,
            aborted_at=observation.observed_at,
        )

    @override
    async def pending_observation(self, job: JobSnapshotDTO) -> JobEffectObservationDTO | None:
        self.events.append("proof")
        return self.observation

    @override
    async def consume_effect(
        self, job: JobSnapshotDTO, observation: JobEffectObservationDTO
    ) -> None:
        self.events.append("consume")
        self.observation = replace(observation, consumed_at=observation.observed_at)
        self.job = replace(job, pending_effect=None)

    @override
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO:
        self.events.append("fence")
        if self.fence_error:
            raise JobFenceLostError()
        return self.job

    @override
    async def peek_candidate(self) -> JobSnapshotDTO | None:
        return self.job

    @override
    async def next_candidate(self) -> JobSnapshotDTO | None:
        return self.job

    @override
    async def retire_attempt(
        self, job: JobSnapshotDTO, *, status: JobStatus, reason: str, due_at: datetime
    ) -> None:
        self.events.append("retire")
        self.job = replace(self.job, status=status, reason=reason, due_at=due_at)

    @override
    async def admit(
        self,
        *,
        operation_id: OperationId,
        request_id: RequestId,
        authority: AdmittedWorkAuthorityDTO,
        payload: JobPayload,
        capacity: int,
    ) -> JobAdmissionDTO:
        raise AssertionError("Unexpected product admission.")

    @override
    async def find(self, operation_id: OperationId) -> JobSnapshotDTO | None:
        raise AssertionError("Unexpected business-operation lookup.")

    @override
    async def start_attempt(
        self, job: JobSnapshotDTO, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO:
        raise AssertionError("Recovery cannot dispatch or start an attempt.")

    @override
    async def checkpoint(
        self, context: JobAttemptContextDTO, data: bytes, *, lease_seconds: float
    ) -> None:
        raise AssertionError("Recovery cannot publish a checkpoint.")

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        raise AssertionError("Use atomic invocation registration.")

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        raise AssertionError("Abort proof is not result confirmation.")

    @override
    async def finish(
        self, context: JobAttemptContextDTO, *, status: JobStatus, reason: str | None
    ) -> None:
        raise AssertionError("Recovery cannot save using the expired live context.")

    @override
    async def request_cancel(self, job_id: JobId) -> None:
        raise AssertionError("Recovery does not request cancellation.")


class MockEffectTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.commit_error: Exception | None = None

    @asynccontextmanager
    async def _begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        if self.commit_error is not None:
            raise self.commit_error
        self.events.append("commit")

    @override
    def begin(self) -> AbstractAsyncContextManager[None]:
        return self._begin()


class MockEffectProductAuthority(AdmittedWorkAuthorizer):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.denied = False

    @override
    async def require_current(self, authority: AdmittedWorkAuthorityDTO) -> None:
        self.events.append("product")
        if self.denied:
            raise AccessDeniedError("The original authority changed.")


class MockEffectCleanupAuthority(ArtifactCleanupAuthorizer):
    def __init__(self, store: MockEffectStore) -> None:
        self.store = store
        self.denied = False
        binding = store.binding.context.binding
        assert isinstance(binding, ArtifactCleanupJobBindingDTO)
        self.facts = ArtifactCleanupFactsDTO(
            binding,
            store.job.job_id,
            (store.binding.artifact_attempt_id,),
            True,
            False,
            False,
            False,
            False,
        )

    @override
    async def require_current(
        self, job_id: JobId, binding: ArtifactCleanupJobBindingDTO
    ) -> ArtifactCleanupFactsDTO:
        self.store.events.append("cleanup")
        if self.denied:
            raise AccessDeniedError("The original obligation changed.")
        return self.facts
