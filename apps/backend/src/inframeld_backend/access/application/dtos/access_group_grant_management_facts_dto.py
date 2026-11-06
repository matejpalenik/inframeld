from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class AccessGroupGrantManagementFactsDTO(AuthorizedOperationScope[ProjectId]):
    """Observe one exact target after the Organization and Project coordination turn."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    group_id: AccessGroupId
    action_id: ActionId
    access_revision: int
    actor: ProjectActionFactsDTO
    actor_can_grant: bool
    actor_is_group_member: bool
    actor_is_group_manager: bool
    recipient: Principal | None
    recipient_is_project_member: bool
    recipient_has_pending_recovery: bool
    recipient_has_coherent_identity: bool
    recipient_application_is_bound: bool
    assignment: ActionGrantState
    grantors: tuple[ProjectDepartureCandidatePolicyInput, ...]
