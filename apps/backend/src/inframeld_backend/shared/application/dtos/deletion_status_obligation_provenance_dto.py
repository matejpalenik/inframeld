from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class DeletionStatusObligationProvenanceDTO:
    """Describe retained owner evidence of an unfinished original cleanup obligation.

    This read projection cannot authorize cleanup or establish its source proof.
    The owning producer must validate that proof before recording this evidence.
    """

    obligation_id: UUID
    operation_id: OperationId
    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    initiator_principal_id: PrincipalId
    observed_at: datetime
    source_revision: int
