from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class StrandedAuthorityRepairFactsDTO:
    installation_id: InstallationId
    recipient: Principal
    responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO
    project_status: ProjectStatus | None
    access_revision: int
    is_project_member: bool
    has_pending_recovery: bool
    oauth_credential_facts: HumanCredentialFactsDTO
    eligible_grantor_exists: bool | None
    target_exists: bool
    target_accepts_assignment: bool
    observed_at: datetime
