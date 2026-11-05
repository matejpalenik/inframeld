from collections.abc import AsyncIterable

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactIntegrityError,
    ArtifactReservationError,
)
from inframeld_backend.shared.application.protocols.artifact_preparation_io import (
    ArtifactPreparationIO,
)
from inframeld_backend.shared.application.protocols.artifact_preparation_records import (
    ArtifactPreparationRecords,
)


class ArtifactPreparationService:
    """Prepare one private original artifact, without granting source admission."""

    def __init__(
        self, attempts: ArtifactPreparationRecords, content: ArtifactPreparationIO
    ) -> None:
        self._attempts, self._content = attempts, content

    async def prepare(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes]
    ) -> VerifiedArtifactDTO:
        return await self._prepare(allocation, chunks)

    async def resume(self, allocation: ArtifactAllocationDTO) -> VerifiedArtifactDTO:
        return await self._prepare(allocation, None)

    async def _prepare(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes] | None
    ) -> VerifiedArtifactDTO:
        async with self._content.hold(allocation):
            facts = await self._attempts.inspect(allocation)
            original = allocation.reservation
            if (
                (
                    facts.reservation_id,
                    facts.artifact_id,
                    facts.attempt_id,
                    facts.scope,
                    facts.limit_bytes,
                    facts.expires_at,
                )
                != (
                    original.reservation_id,
                    original.artifact_id,
                    original.attempt_id,
                    original.scope,
                    original.limit_bytes,
                    original.expires_at,
                )
                or facts.retired
                or facts.released
                or facts.expires_at <= facts.observed_at
            ):
                raise ArtifactReservationError("The original private reservation is unavailable.")
            if facts.length is None or facts.digest is None:
                if facts.length is not None or facts.digest is not None or chunks is None:
                    raise ArtifactIntegrityError("The original complete seal cannot be confirmed.")
                attempt = await self._content.stage(allocation, chunks)
                if (
                    (attempt.artifact_id, attempt.attempt_id, attempt.scope)
                    != (original.artifact_id, original.attempt_id, original.scope)
                    or type(attempt.length) is not int
                    or not 0 <= attempt.length <= original.limit_bytes
                ):
                    raise ArtifactIntegrityError("Staging returned another original target.")
                await self._attempts.seal(allocation, attempt)
            else:
                if chunks is not None:
                    raise ArtifactReservationError(
                        "A sealed original resumes without replacement input."
                    )
                attempt = ArtifactAttemptDTO(
                    facts.artifact_id, facts.attempt_id, facts.scope, facts.length, facts.digest
                )
            upload = await self._attempts.begin_put(allocation, attempt)
            verified = await self._content.verify(attempt, upload=upload)
            if verified.attempt != attempt:
                raise ArtifactIntegrityError("Readback verified another original target.")
            await self._attempts.confirm_verified(allocation, verified)
            return verified
