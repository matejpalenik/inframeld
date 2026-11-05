from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId


@dataclass(frozen=True, slots=True)
class ArtifactCleanupTargetDTO:
    """Observe the original owned target without strengthening an unsealed expectation."""

    artifact_id: ArtifactId
    attempt_id: ArtifactAttemptId
    scope: ArtifactScopeDTO
    length: int | None
    digest: ArtifactContentDigest | None
