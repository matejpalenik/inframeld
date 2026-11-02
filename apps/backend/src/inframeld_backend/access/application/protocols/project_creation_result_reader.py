from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProjectCreationResultReader(Protocol):
    @abstractmethod
    async def original(
        self, *, organization_id: OrganizationId, actor_id: PrincipalId, operation_id: OperationId
    ) -> CreatedProjectDTO:
        """Read the typed original result under the authorized reservation and expiry.

        The original reservation remains Organization-scoped with no Project ID.
        Fail on missing/incoherent results. Never reconstruct names or initial
        grants from today's Project, retarget the reservation or refresh expiry.
        """
        ...
