from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId


class JobEffectObservationRecorder(Protocol):
    """Admit one exact invocation and retain only adapter-proved exclusion.

    Admission returns only after a first, non-replayable committed claim. A
    duplicate, lost acknowledgment or expired original fence supplies no grant.
    Only the adapter's winning abort gate calls a recording method. Each call
    owns a fresh short transaction on the event loop, outside native SDK work.
    """

    @abstractmethod
    async def admit_put(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None: ...

    @abstractmethod
    async def admit_delete(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None: ...

    @abstractmethod
    async def record_put_abort(
        self, observation: JobEffectId, attempt: ArtifactAttemptDTO
    ) -> None: ...

    @abstractmethod
    async def record_delete_abort(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None: ...
