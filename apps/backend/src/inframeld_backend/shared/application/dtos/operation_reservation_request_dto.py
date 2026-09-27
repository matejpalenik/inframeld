from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


@dataclass(frozen=True, slots=True)
class OperationReservationRequestDTO:
    """Carry a verified caller and an already-computed request fingerprint."""

    principal_id: PrincipalId
    organization_id: OrganizationId
    project_id: ProjectId | None
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    requested_route: str
    key: IdempotencyKey
    fingerprint: bytes
