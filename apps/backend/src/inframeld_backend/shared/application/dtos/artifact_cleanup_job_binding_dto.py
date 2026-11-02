from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)


@dataclass(frozen=True, slots=True)
class ArtifactCleanupJobBindingDTO:
    """Bind cleanup to immutable obligation meaning, never an incoming principal."""

    obligation_id: ArtifactCleanupObligationId
    scope: ArtifactScopeDTO
    kind: ArtifactCleanupKind
    origin: BusinessOperationArtifactOriginDTO | UnadmittedStagingArtifactOriginDTO
