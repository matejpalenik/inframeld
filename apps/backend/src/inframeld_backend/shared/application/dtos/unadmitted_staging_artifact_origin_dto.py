from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.request_id import RequestId


@dataclass(frozen=True, slots=True)
class UnadmittedStagingArtifactOriginDTO:
    """Attribute private staging that has no admitted business operation."""

    attempt_id: ArtifactAttemptId
    request_id: RequestId
