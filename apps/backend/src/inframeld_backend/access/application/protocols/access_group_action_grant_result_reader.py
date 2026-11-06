from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.remove_access_group_action_grant_command import (
    RemoveAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_access_group_action_grant_command import (
    SetAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_group_action_grant_change_result_dto import (
    AccessGroupActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class AccessGroupActionGrantResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        facts: AccessGroupGrantManagementFactsDTO,
        command: SetAccessGroupActionGrantCommand | RemoveAccessGroupActionGrantCommand,
        context: IdempotencyContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> AccessGroupActionGrantChangeResultDTO:
        """Read only this authorized original receipt, independent of current assignments.

        Retained operation, actor, scope, action, method and outcome must agree.
        Missing or inconsistent original results are conflicts, not fresh work.
        """
        ...
