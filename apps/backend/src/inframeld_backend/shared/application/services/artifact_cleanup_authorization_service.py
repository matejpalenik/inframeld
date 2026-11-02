from typing import override

from inframeld_backend.shared.application.dtos.artifact_cleanup_facts_dto import (
    ArtifactCleanupFactsDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.protocols.artifact_cleanup_authorizer import (
    ArtifactCleanupAuthorizer,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_facts_reader import (
    ArtifactCleanupFactsReader,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId


class ArtifactCleanupAuthorizationService(ArtifactCleanupAuthorizer):
    def __init__(self, facts: ArtifactCleanupFactsReader) -> None:
        self._facts = facts

    @override
    async def require_current(
        self, job_id: JobId, binding: ArtifactCleanupJobBindingDTO
    ) -> ArtifactCleanupFactsDTO:
        facts = await self._facts.read(binding.obligation_id)
        if (
            facts is None
            or facts.binding != binding
            or facts.job_id != job_id
            or not facts.owns_targets
            or not facts.targets
        ):
            raise AccessDeniedError("The original cleanup obligation cannot be confirmed.")

        if isinstance(binding.origin, UnadmittedStagingArtifactOriginDTO) and facts.targets != (
            binding.origin.attempt_id,
        ):
            raise AccessDeniedError("Unadmitted staging authority belongs to one exact attempt.")
        if (
            binding.kind is not ArtifactCleanupKind.ABANDONED_STAGING
            and not facts.retirement_authorized
        ):
            raise AccessDeniedError("Cleanup requires the original persisted retirement proof.")
        if (
            binding.kind is ArtifactCleanupKind.RETENTION_EXPIRY
            and not facts.retention_allows_cleanup
        ):
            raise AccessDeniedError("Protected retention still requires these artifacts.")

        return facts
