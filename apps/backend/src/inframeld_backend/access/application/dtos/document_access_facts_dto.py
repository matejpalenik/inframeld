from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_key_current_facts_dto import (
    ApplicationKeyCurrentFactsDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class DocumentAccessFactsDTO:
    """Current Access observations, not a reusable authorization decision."""

    principal: Principal
    organization_id: OrganizationId
    project_id: ProjectId
    project_status: ProjectStatus
    is_project_member: bool
    has_pending_recovery: bool
    oauth_credential_facts: HumanCredentialFactsDTO | None
    valid_group_ids: frozenset[AccessGroupId]
    member_group_ids: frozenset[AccessGroupId]
    application_key_facts: ApplicationKeyCurrentFactsDTO | None = None
