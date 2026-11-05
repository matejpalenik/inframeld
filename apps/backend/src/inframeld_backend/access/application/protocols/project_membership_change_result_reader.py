from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


class ProjectMembershipChangeResultReader(Protocol):
    @abstractmethod
    async def load_original_membership_result(
        self,
        *,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
        change_kind: ProjectMembershipChangeKind,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectMembershipChangeResultDTO:
        """Validate original business facts and reservation binding without membership lookup."""
        ...
