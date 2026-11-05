from dataclasses import replace
from typing import override

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactStagingBusyError
from inframeld_backend.shared.application.errors.job_errors import (
    JobStoppedError,
    SafeJobRetryError,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_preparer import (
    ArtifactCleanupPreparer,
)
from inframeld_backend.shared.application.protocols.artifact_local_cleanup import (
    ArtifactLocalCleanup,
)
from inframeld_backend.shared.application.protocols.artifact_staging import ArtifactStaging
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_handler import JobHandler


class ArtifactCleanupJobHandler(JobHandler):
    """Dispatch one prepared DELETE and checkpoint its acknowledgment, never physical settlement."""

    def __init__(
        self,
        artifact_cleanup_preparer: ArtifactCleanupPreparer,
        artifact_store: ArtifactStore,
        artifact_local_cleanup: ArtifactLocalCleanup,
        artifact_staging: ArtifactStaging,
    ) -> None:
        self._artifact_cleanup_preparer = artifact_cleanup_preparer
        self._artifact_store = artifact_store
        self._artifact_local_cleanup = artifact_local_cleanup
        self._artifact_staging = artifact_staging

    @override
    def payload_type(self) -> tuple[str, int]:
        return "artifact.cleanup", 1

    @override
    async def run(self, context: JobAttemptContextDTO, checkpoints: JobCheckpoints) -> None:
        local = await self._artifact_local_cleanup.prepare_local(context)
        if local is not None:
            try:
                await self._artifact_staging.remove(local)
            except ArtifactStagingBusyError as error:
                raise SafeJobRetryError(
                    "The retired local target still has an active holder."
                ) from error
            await self._artifact_local_cleanup.confirm_local(context, local)
        prepared = await self._artifact_cleanup_preparer.prepare(context)
        if prepared is None:
            return

        binding = prepared.context.binding
        if (
            prepared.action != JobEffectAction.DELETE
            or not isinstance(binding, ArtifactCleanupJobBindingDTO)
            or binding.kind is not ArtifactCleanupKind.ABANDONED_STAGING
            or replace(prepared.context, checkpoint=context.checkpoint) != context
            or prepared.scope != binding.scope
            or (
                prepared.context.payload.kind,
                prepared.context.payload.version,
                prepared.context.payload.data,
            )
            != ("artifact.cleanup", 1, binding.obligation_id.value.bytes)
            or (
                isinstance(binding.origin, UnadmittedStagingArtifactOriginDTO)
                and binding.origin.attempt_id != prepared.artifact_attempt_id
            )
        ):
            raise JobStoppedError("The prepared DELETE differs from the original cleanup work.")

        await self._artifact_store.delete(
            prepared.scope, prepared.artifact_attempt_id, observation=prepared.effect_id
        )
        acknowledgment = (
            b"artifact.cleanup.delete-ack.v1\0"
            + binding.obligation_id.value.bytes
            + prepared.artifact_id.value.bytes
            + prepared.artifact_attempt_id.value.bytes
        )
        await checkpoints.confirm_effect(prepared.context, prepared.unit, acknowledgment)
