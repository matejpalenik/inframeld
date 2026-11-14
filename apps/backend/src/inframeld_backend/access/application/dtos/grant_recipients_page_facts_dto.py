from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.grant_recipient_candidate_dto import (
    GrantRecipientCandidateDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class GrantRecipientsPageFactsDTO:
    """Retain current authority facts even when the eligible member page is empty."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    target: (
        ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO
        | ModelConnectionGrantTargetDTO
    )
    action_id: ActionId
    actor: ProjectActionFactsDTO
    actor_can_grant: bool
    actor_group_relationships: AccessGroupRelationships | None
    items: tuple[GrantRecipientCandidateDTO, ...]
