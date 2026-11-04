from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)


class ProjectMembershipChanger(Protocol):
    """Own atomic membership changes, current authority and original-result recovery."""

    @abstractmethod
    async def add_member(
        self,
        *,
        access: AccessContextDTO,
        command: AddProjectMemberCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        """Add only bare membership for an eligible admitted human, or recover its result."""
        ...

    @abstractmethod
    async def remove_member(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectMemberCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        """Remove recipient relationships after safe handover, without deleting shared work."""
        ...
