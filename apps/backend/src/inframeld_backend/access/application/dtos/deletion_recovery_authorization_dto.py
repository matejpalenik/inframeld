from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class DeletionRecoveryAuthorizationDTO:
    """Identify the currently eligible human before searching any deletion history."""

    installation_id: InstallationId
    organization_id: OrganizationId
    principal_id: PrincipalId
