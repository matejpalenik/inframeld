from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO


@dataclass(frozen=True, slots=True)
class VerifiedArtifactDTO:
    """Report complete matching readback, without publication or cleanup authority."""

    attempt: ArtifactAttemptDTO
