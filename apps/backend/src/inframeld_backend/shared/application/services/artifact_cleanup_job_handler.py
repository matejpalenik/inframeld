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
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
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
        preparer: ArtifactCleanupPreparer,
        artifacts: ArtifactStore,
        local: ArtifactLocalCleanup,
        staging: ArtifactStaging,
    ) -> None:
        self._preparer = preparer
        self._artifacts = artifacts
        self._local, self._staging = local, staging

    @override
    def payload_type(self) -> tuple[str, int]:
        return "artifact.cleanup", 1

    @override
    async def run(self, context: JobAttemptContextDTO, checkpoints: JobCheckpoints) -> None:
        local = await self._local.prepare_local(context)
        if local is not None:
            await self._staging.remove(local)
            await self._local.confirm_local(context, local)
        prepared = await self._preparer.prepare(context)
        if prepared is None:
            return

        binding = prepared.context.binding
        if (
            prepared.action != "delete"
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

        await self._artifacts.delete(
            prepared.scope, prepared.artifact_attempt_id, observation=prepared.effect_id
        )
        acknowledgment = (
            b"artifact.cleanup.delete-ack.v1\0"
            + binding.obligation_id.value.bytes
            + prepared.artifact_id.value.bytes
            + prepared.artifact_attempt_id.value.bytes
        )
        await checkpoints.confirm_effect(prepared.context, prepared.unit, acknowledgment)
