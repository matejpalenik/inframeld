from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectDeletionResultDTO:
    """Retain original 202 acceptance, not shutdown or physical-erasure completion."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    actor_principal_id: PrincipalId
    obligation_id: ProjectDeletionObligationId
    job_id: JobId
    before_access_revision: int
    access_revision: int
    operation: AcceptedAsyncOperationDTO
