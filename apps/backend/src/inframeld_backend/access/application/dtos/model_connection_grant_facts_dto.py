from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ModelConnectionGrantFactsDTO(AuthorizedOperationScope[ProjectId]):
    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    model_connection_id: ModelConnectionId
    action: ModelConnectionAction
    access_revision: int
    actor: ProjectActionFactsDTO
    actor_can_grant: bool
    recipient: Principal | None
    recipient_is_project_member: bool
    recipient_has_pending_recovery: bool
    recipient_has_coherent_identity: bool
    application_is_project_bound: bool
    assignment: ActionGrantState
    grantors: tuple[ProjectDepartureCandidatePolicyInput, ...]
