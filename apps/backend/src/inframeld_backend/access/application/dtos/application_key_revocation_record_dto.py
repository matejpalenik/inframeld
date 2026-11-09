from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ApplicationKeyRevocationRecordDTO:
    """Retain an immutable safe receipt independent of later key lifecycle changes."""

    operation_id: OperationId
    organization_id: OrganizationId
    installation_id: InstallationId
    actor_principal_id: PrincipalId
    access_revision: int
    metadata: ApplicationKeyMetadataDTO
