from abc import abstractmethod
from collections.abc import AsyncGenerator
from typing import BinaryIO, Protocol

from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_listing_dto import ArtifactListingDTO
from inframeld_backend.shared.application.dtos.artifact_object_dto import ArtifactObjectDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId


class ArtifactStore(Protocol):
    """Access exact private objects, never product admission or physical-erasure completion.

    Callers retain the original sealed expectation and commit unresolved-write
    evidence before PUT. Lost acknowledgments, timeouts and cancellation cannot
    authorize replacement identity, absence, publication or reservation release.
    A supplied observation requires one committed invocation admission before
    scheduling. Only the adapter's excluded-entry gate may record its abort.
    Unobserved calls produce no job-recovery proof. An implementation unable to
    honor an observation must reject it rather than silently run unobserved.
    """

    @abstractmethod
    async def put(
        self,
        attempt: ArtifactAttemptDTO,
        content: BinaryIO,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        """Conditionally create the original object, never overwrite an existing key.

        Keep content open until native calls drain after an unknown outcome.
        Reconcile the same attempt through complete readback before publication.
        """
        ...

    @abstractmethod
    def read(self, attempt: ArtifactAttemptDTO) -> AsyncGenerator[bytes]: ...

    @abstractmethod
    async def head(
        self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactObjectDTO | None: ...

    @abstractmethod
    async def list(
        self, scope: ArtifactScopeDTO, *, after: ArtifactAttemptId | None, limit: int
    ) -> ArtifactListingDTO: ...

    @abstractmethod
    async def delete(
        self,
        scope: ArtifactScopeDTO,
        attempt_id: ArtifactAttemptId,
        *,
        observation: JobEffectId | None = None,
    ) -> None: ...
