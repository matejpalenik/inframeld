from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.domain.entities.project_metadata import ProjectMetadata
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProjectMetadataRepository(Protocol):
    """Load a scoped aggregate and persist its transition in the same caller transaction.

    Save enforces expected revision/name uniqueness and commits neither audit nor state.
    Original results are scoped to the same Project and reservation.
    """

    @abstractmethod
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectMetadata: ...

    @abstractmethod
    async def save(
        self,
        metadata: ProjectMetadata,
        *,
        expected_revision: int,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None: ...

    @abstractmethod
    async def original(
        self, *, organization_id: OrganizationId, project_id: ProjectId, operation_id: OperationId
    ) -> ProjectMetadataDTO: ...
