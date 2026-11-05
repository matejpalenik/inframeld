from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectActionGrantManagementFactsDTO:
    """Observe exact-action administration under the owning Access locks."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    action_id: ActionId
    grant: ProjectGrantChangeFactsDTO
    recipient_has_pending_recovery: bool
    recipient_has_coherent_identity: bool
    recipient_application_is_project_bound: bool
    other_grantors: tuple[ProjectDepartureCandidatePolicyInput, ...]
