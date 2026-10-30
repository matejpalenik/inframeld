from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class AdmittedWorkAuthorityDTO:
    """Fix the original actor and scope without retaining an incoming credential.

    A stored admission is not permission. Current ownership and Access checks
    are required before every protected step and publication.
    """

    principal_id: PrincipalId
    principal_kind: PrincipalKind
    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    action_id: ActionId
    human_binding: HumanOAuthCredentialBindingDTO | None
