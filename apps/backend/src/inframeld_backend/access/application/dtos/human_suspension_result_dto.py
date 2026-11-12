from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class HumanSuspensionResultDTO:
    """Return the safe original business outcome without reapplying its transition."""

    organization_id: OrganizationId
    principal_id: PrincipalId
    actor_principal_id: PrincipalId
    access_revision: int
    cleanup_operation_id: OperationId
    operation: AcceptedAsyncOperationDTO
