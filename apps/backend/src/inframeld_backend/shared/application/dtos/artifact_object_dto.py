from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId


@dataclass(frozen=True, slots=True)
class ArtifactObjectDTO:
    """Observe one scoped object. Metadata alone does not verify its content."""

    attempt_id: ArtifactAttemptId
    length: int
