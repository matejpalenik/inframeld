from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.remove_organization_action_grant_command import (
    RemoveOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.organization_action_grant_change_result_dto import (
    OrganizationActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class OrganizationActionGrantResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        facts: OrganizationGrantManagementFactsDTO,
        command: SetOrganizationActionGrantCommand | RemoveOrganizationActionGrantCommand,
        context: IdempotencyContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> OrganizationActionGrantChangeResultDTO:
        """Read only this authorized original receipt, independent of current assignments.

        Retained operation, actor, scope, action, method and outcome must agree.
        Missing or inconsistent original results are conflicts, not fresh work.
        """
        ...
