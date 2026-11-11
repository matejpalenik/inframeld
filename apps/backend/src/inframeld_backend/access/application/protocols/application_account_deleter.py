from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_deletion_result_dto import (
    ApplicationAccountDeletionResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ApplicationAccountDeleter(Protocol):
    """Retire one application atomically under current human Delete authority.

    Authorize before history and recover a coherent original before fresh revision
    or lifecycle checks. Retired targets grant no inspection exception. Return
    only after transaction exit. Cancellation, rollback and uncertain commit
    acknowledgment propagate without redispatch or a cleanup job.
    """

    @abstractmethod
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteApplicationAccountCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountDeletionResultDTO: ...
