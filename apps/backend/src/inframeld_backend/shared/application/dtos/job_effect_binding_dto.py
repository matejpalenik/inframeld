from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId


@dataclass(frozen=True, slots=True)
class JobEffectBindingDTO:
    """Retain one original physical invocation without asserting its outcome."""

    effect_id: JobEffectId
    context: JobAttemptContextDTO
    unit: str
    action: JobEffectAction
    artifact_id: ArtifactId
    artifact_attempt_id: ArtifactAttemptId
    scope: ArtifactScopeDTO
    length: int | None
    digest: ArtifactContentDigest | None
