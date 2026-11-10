from abc import abstractmethod
from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from typing import BinaryIO, Protocol

from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)


class ArtifactStaging(Protocol):
    """Stage bounded private bytes against an existing exact capacity reservation.

    Use the original authoritative remaining deadline without sliding it during
    stream consumption or sealing. Disk work must not block unrelated async work.
    Interruption drains the current native call before releasing its handles.
    Partial or interrupted writes remain owned for cleanup. Sealing is not
    remote verification or publication. Removal does not itself release a ledger
    reservation or prove absence of earlier remote writes.
    """

    @abstractmethod
    def hold(self, attempt_id: ArtifactAttemptId) -> AbstractAsyncContextManager[None]: ...

    @abstractmethod
    async def stage(
        self,
        reservation_id: ArtifactStagingReservationId,
        *,
        artifact_id: ArtifactId,
        attempt_id: ArtifactAttemptId,
        scope: ArtifactScopeDTO,
        chunks: AsyncIterable[bytes],
    ) -> ArtifactAttemptDTO: ...

    @abstractmethod
    def open(self, attempt: ArtifactAttemptDTO) -> AbstractAsyncContextManager[BinaryIO]: ...

    @abstractmethod
    async def remove(self, target: ArtifactCleanupTargetDTO) -> None: ...
