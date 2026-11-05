from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)


class ProjectActionGrantResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        facts: ProjectActionGrantManagementFactsDTO,
        command: SetProjectActionGrantCommand | RemoveProjectActionGrantCommand,
        context: OperationAdmissionContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        """Read immutable business facts under the exact live original reservation.

        Require caller transaction, installation/actor/target/action/method/route/
        key/authority binding and matching safe-result expiry. Reject missing,
        expired or incoherent history. Do not inspect current recipient eligibility
        or assignment state and never recreate a grant.
        """
        ...
