from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class ProjectDeleter(Protocol):
    """Admit one human's exact Project deletion and preserve its original acceptance."""

    @abstractmethod
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteProjectCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> ProjectDeletionResultDTO:
        """Own one bounded transaction through commit, with current authority before history.

        Resolve the exact original before fresh revision or capacity admission.
        A new block, revision, audit, original binding, obligation and queue
        admission must commit together. Failure or cancellation propagates for
        rollback. An uncertain commit never triggers automatic redispatch.
        Accepted work retains 202 on replay and says nothing about erasure.
        """
        ...
