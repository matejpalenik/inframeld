from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectMetadataRepairFactsDTO:
    installation_id: InstallationId
    recipient: Principal
    project_id: ProjectId
    project_status: ProjectStatus
    access_revision: int
    is_project_member: bool
    has_pending_recovery: bool
    oauth_credential_facts: HumanCredentialFactsDTO
    eligible_grantor_exists: bool | None
    observed_at: datetime
