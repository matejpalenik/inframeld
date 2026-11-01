from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class DeletionStatusAuthorizationDTO:
    """Carry current human scope before the reader matches the original initiator."""

    operation_id: OperationId
    installation_id: InstallationId
    organization_id: OrganizationId
    principal_id: PrincipalId
