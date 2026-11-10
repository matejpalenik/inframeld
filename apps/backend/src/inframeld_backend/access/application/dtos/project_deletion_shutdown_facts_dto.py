from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectDeletionShutdownFactsDTO:
    """Observe the locked Project and original parent, without granting admission or ownership."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    project_status: ProjectStatus
    access_revision: int
    binding: ProjectDeletionJobBindingDTO
    source_revision: int
    shutdown_completed_at: datetime | None
