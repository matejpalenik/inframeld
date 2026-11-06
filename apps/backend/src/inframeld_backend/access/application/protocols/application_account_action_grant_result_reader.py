from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.remove_application_account_action_grant_command import (
    RemoveApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.application_account_action_grant_change_result_dto import (
    ApplicationAccountActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ApplicationAccountActionGrantResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        facts: ApplicationAccountGrantManagementFactsDTO,
        command: SetApplicationAccountActionGrantCommand
        | RemoveApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        """Read only this authorized original receipt, independent of current assignments.

        Retained operation, actor, scope, action, method and outcome must agree.
        Missing or inconsistent original results are conflicts, not fresh work.
        """
        ...
