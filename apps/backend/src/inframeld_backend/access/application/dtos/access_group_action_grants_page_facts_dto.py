from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_action_grant_dto import (
    AccessGroupActionGrantDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class AccessGroupActionGrantsPageFactsDTO:
    """Observe the current authority header even for an empty bounded assignment page."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    group_id: AccessGroupId
    action_id: ActionId
    actor_can_grant: bool
    actor: ProjectActionFactsDTO
    actor_is_group_member: bool
    actor_is_group_manager: bool
    items: tuple[AccessGroupActionGrantDTO, ...]
