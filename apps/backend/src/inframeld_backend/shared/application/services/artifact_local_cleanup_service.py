from typing import override

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.protocols.artifact_attempt_repository import (
    ArtifactAttemptRepository,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_authorizer import (
    ArtifactCleanupAuthorizer,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_target_reader import (
    ArtifactCleanupTargetReader,
)
from inframeld_backend.shared.application.protocols.artifact_local_cleanup import (
    ArtifactLocalCleanup,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class ArtifactLocalCleanupService(ArtifactLocalCleanup):
    """Retire local growth before joining holders, retaining all remote uncertainty."""

    def __init__(
        self,
        transactions: TransactionManager,
        jobs: JobStore,
        authority: ArtifactCleanupAuthorizer,
        targets: ArtifactCleanupTargetReader,
        attempts: ArtifactAttemptRepository,
    ) -> None:
        self._transactions, self._jobs, self._authority = transactions, jobs, authority
        self._targets, self._attempts = targets, attempts

    @override
    async def prepare_local(self, context: JobAttemptContextDTO) -> ArtifactCleanupTargetDTO | None:
        async with self._transactions.begin():
            binding, target = await self._guard(context)
            return target if await self._attempts.retire_local(binding, target) else None

    @override
    async def confirm_local(
        self, context: JobAttemptContextDTO, target: ArtifactCleanupTargetDTO
    ) -> None:
        async with self._transactions.begin():
            binding, current = await self._guard(context)
            if target != current:
                raise ConflictError("The original local target changed during removal.")
            await self._attempts.confirm_local_removed(binding, target)

    async def _guard(
        self, context: JobAttemptContextDTO
    ) -> tuple[ArtifactCleanupJobBindingDTO, ArtifactCleanupTargetDTO]:
        binding = context.binding
        if (
            not isinstance(binding, ArtifactCleanupJobBindingDTO)
            or binding.kind is not ArtifactCleanupKind.ABANDONED_STAGING
            or (context.payload.kind, context.payload.version, context.payload.data)
            != ("artifact.cleanup", 1, binding.obligation_id.value.bytes)
        ):
            raise JobStoppedError("Local cleanup requires its original abandoned-staging payload.")
        current = await self._jobs.require_current(context)
        if (current.binding, current.payload, current.work_deadline) != (
            binding,
            context.payload,
            context.work_deadline,
        ):
            raise JobFenceLostError("The original cleanup work changed.")
        facts = await self._authority.require_current(context.job_id, binding)
        if (
            facts.binding != binding
            or facts.job_id != context.job_id
            or not facts.owns_targets
            or len(facts.targets) != 1
            or facts.published
            or not facts.retention_allows_cleanup
            or (
                isinstance(binding.origin, UnadmittedStagingArtifactOriginDTO)
                and facts.targets != (binding.origin.attempt_id,)
            )
        ):
            raise AccessDeniedError("The original single local target cannot be retired.")
        target = await self._targets.read(binding, facts.targets[0])
        if (
            target is None
            or target.attempt_id != facts.targets[0]
            or target.scope != binding.scope
            or ((target.length is None) != (target.digest is None))
            or (target.length is not None and (type(target.length) is not int or target.length < 0))
        ):
            raise ConflictError("The original nullable local expectation cannot be confirmed.")
        return binding, target
