from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ProjectDeletionResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        installation_id: InstallationId,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation: AcceptedAsyncOperationDTO,
    ) -> ProjectDeletionResultDTO:
        """Read the immutable original after current ordinary Delete-project authorization.

        Verify the retained reservation, obligation, job and original human
        binding. Missing or incoherent required history fails closed rather than
        reconstructing acceptance from today's Project. Use caller transaction
        and deadline. Narrow initiator-only content-free status stays separate.
        """
        ...
