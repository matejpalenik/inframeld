import hashlib
from contextlib import aclosing

from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
)
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore


class ArtifactVerificationService:
    """Compare complete readback with the original trusted expectation outside SQL."""

    def __init__(
        self, artifact_store: ArtifactStore, *, max_bytes: int = 256 * 1024 * 1024
    ) -> None:
        if type(max_bytes) is not int or not 0 < max_bytes <= 256 * 1024 * 1024:
            raise ValueError("The artifact verification bound is outside the supported profile.")
        self._artifact_store = artifact_store
        self._max_bytes = max_bytes

    async def verify(self, attempt: ArtifactAttemptDTO) -> VerifiedArtifactDTO:
        if type(attempt.length) is not int or attempt.length < 0:
            raise ArtifactIntegrityError("The sealed artifact length is invalid.")
        if attempt.length > self._max_bytes:
            raise ArtifactCapacityError("The sealed artifact exceeds its verification bound.")

        digest = hashlib.sha256()
        length = 0
        async with aclosing(self._artifact_store.read(attempt)) as content:
            async for chunk in content:
                if type(chunk) is not bytes:
                    raise ArtifactIntegrityError("Readback did not provide immutable bytes.")
                length += len(chunk)
                if length > attempt.length:
                    raise ArtifactIntegrityError("Readback exceeds the sealed artifact length.")
                digest.update(chunk)

        if length != attempt.length or digest.digest() != attempt.digest.value:
            raise ArtifactIntegrityError("Readback differs from the sealed artifact content.")
        return VerifiedArtifactDTO(attempt)
