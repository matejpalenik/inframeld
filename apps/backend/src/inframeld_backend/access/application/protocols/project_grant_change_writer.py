from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProjectGrantChangeWriter(Protocol):
    """Persist an authorized project grant change in the caller's transaction."""

    @abstractmethod
    async def create_use_only(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        expected_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        """Create the grant, advance the revision, and audit; never commit."""
        ...
