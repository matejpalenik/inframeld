from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_grant_dto import (
    MyProjectAccessGrantDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_relationship_dto import (
    MyProjectAccessRelationshipDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class MyProjectAccessFactsDTO:
    """Keep one current authorization/revision header with its combined page."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    actor: Principal
    has_pending_recovery: bool
    oauth_credential_facts: HumanCredentialFactsDTO | None
    project_status: ProjectStatus
    is_project_member: bool
    items: tuple[MyProjectAccessGrantDTO | MyProjectAccessRelationshipDTO, ...]
