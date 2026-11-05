from dataclasses import replace
from typing import override
from uuid import uuid4

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_authorizer import (
    ArtifactCleanupAuthorizer,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_preparer import (
    ArtifactCleanupPreparer,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_target_reader import (
    ArtifactCleanupTargetReader,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId


class ArtifactCleanupPreparationService(ArtifactCleanupPreparer):
    """Commit one exact pending invocation or recover its authoritative saved acknowledgment."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        job_store: JobStore,
        artifact_cleanup_authorizer: ArtifactCleanupAuthorizer,
        artifact_cleanup_target_reader: ArtifactCleanupTargetReader,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._job_store = job_store
        self._artifact_cleanup_authorizer = artifact_cleanup_authorizer
        self._artifact_cleanup_target_reader = artifact_cleanup_target_reader

    @override
    async def prepare(self, context: JobAttemptContextDTO) -> JobEffectBindingDTO | None:
        async with self._transaction_manager.begin():
            binding = context.binding
            if (
                not isinstance(binding, ArtifactCleanupJobBindingDTO)
                or binding.kind is not ArtifactCleanupKind.ABANDONED_STAGING
                or (context.payload.kind, context.payload.version, context.payload.data)
                != ("artifact.cleanup", 1, binding.obligation_id.value.bytes)
            ):
                raise JobStoppedError("Cleanup requires its original abandoned-staging payload.")

            current = await self._job_store.require_current(context)
            if (current.binding, current.payload, current.work_deadline) != (
                binding,
                context.payload,
                context.work_deadline,
            ):
                raise JobFenceLostError("The original cleanup work changed.")
            facts = await self._artifact_cleanup_authorizer.require_current(context.job_id, binding)
            if (
                facts.binding != binding
                or facts.job_id != context.job_id
                or not facts.owns_targets
                or len(facts.targets) != 1
                or facts.published
                or facts.pending_write
                or not facts.retention_allows_cleanup
                or (
                    isinstance(binding.origin, UnadmittedStagingArtifactOriginDTO)
                    and facts.targets != (binding.origin.attempt_id,)
                )
            ):
                raise AccessDeniedError("The original single cleanup target is not available.")
            if current.pending_effect is not None:
                raise ConflictError("An original physical invocation remains unresolved.")

            target = await self._artifact_cleanup_target_reader.read(binding, facts.targets[0])
            if (
                target is None
                or target.attempt_id != facts.targets[0]
                or target.scope != binding.scope
                or ((target.length is None) != (target.digest is None))
                or (
                    target.length is not None
                    and (type(target.length) is not int or target.length < 0)
                )
            ):
                raise ConflictError("The original artifact expectation cannot be confirmed.")
            acknowledgment = (
                b"artifact.cleanup.delete-ack.v1\0"
                + binding.obligation_id.value.bytes
                + target.artifact_id.value.bytes
                + target.attempt_id.value.bytes
            )
            if current.checkpoint == acknowledgment:
                return None
            if current.checkpoint:
                raise ConflictError(
                    "The retained cleanup checkpoint is not its exact acknowledgment."
                )

            prepared = JobEffectBindingDTO(
                JobEffectId(uuid4()),
                replace(context, checkpoint=current.checkpoint),
                "artifact.cleanup:" + target.attempt_id.value.hex,
                JobEffectAction.DELETE,
                target.artifact_id,
                target.attempt_id,
                target.scope,
                target.length,
                target.digest,
            )
            await self._job_store.register_effect(prepared)
            return prepared
