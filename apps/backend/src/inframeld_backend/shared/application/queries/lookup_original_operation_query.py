from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class LookupOriginalOperationQuery:
    """Correlate an original request under an independently authorized expected guard."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId | None
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    requested_route: str
    key: IdempotencyKey
    expected_authority: OperationLookupAuthority
