from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.policy_inputs.organization_grant_candidate_policy_input import (
    OrganizationGrantCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class OrganizationGrantManagementFactsDTO(AuthorizedOperationScope[None]):
    """Observe one coordinated Organization grant attempt, without authorizing it."""

    installation_id: InstallationId
    organization_id: OrganizationId
    action_id: ActionId
    access_revision: int
    actor: Principal
    actor_can_grant: bool
    actor_has_pending_recovery: bool
    actor_oauth_credential_facts: HumanCredentialFactsDTO | None
    recipient: Principal | None
    recipient_has_pending_recovery: bool
    recipient_has_coherent_identity: bool
    assignment: ActionGrantState
    other_grantors: tuple[OrganizationGrantCandidatePolicyInput, ...]
    project_id: None = None
