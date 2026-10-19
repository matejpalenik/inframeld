from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectGrantAuthorizer(Protocol):
    """Authorize grant assignments under the caller's Access transaction."""

    @abstractmethod
    async def require_use_only_assignment(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantAuthorizationDTO:
        """Require current authority to assign the exact action to a human.

        Hide unavailable projects before reporting authority failures. Check
        the grantor before revealing whether the recipient exists.

        The caller must authorize before reserving work or returning a replay.
        Keep the acquired locks until commit or rollback. This operation does
        not create a grant or commit the transaction.
        """
        ...
