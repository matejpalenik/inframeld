from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.artifact_object_dto import ArtifactObjectDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId


@dataclass(frozen=True, slots=True)
class ArtifactListingDTO:
    objects: tuple[ArtifactObjectDTO, ...]
    after: ArtifactAttemptId | None
