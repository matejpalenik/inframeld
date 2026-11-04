from abc import abstractmethod
from typing import Literal, Protocol

from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
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
        change_kind: Literal["add", "remove"],
        operation_id: OperationId,
    ) -> None:
        """Save checked recipient-only effects, revision, audit and original business receipt.

        The caller owns the coordinated transaction, completion and rollback.
        """
        ...
