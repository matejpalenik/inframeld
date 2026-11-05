from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProjectMembershipChangeWriter(Protocol):
    @abstractmethod
    async def save(
        self,
        *,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
        change_kind: ProjectMembershipChangeKind,
        operation_id: OperationId,
    ) -> None:
        """Save checked recipient-only effects, revision, audit and original business receipt.

        The caller owns the coordinated transaction, completion and rollback.
        """
        ...
