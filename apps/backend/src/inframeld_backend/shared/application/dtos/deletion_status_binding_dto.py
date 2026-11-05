from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class DeletionStatusBindingDTO:
    """Retain original reservation correlation, never proof of admitted deletion."""

    operation_id: OperationId
    request_id: RequestId
    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    initiator_principal_id: PrincipalId
    method: HttpMethod
    requested_route: str
    key: IdempotencyKey
    fingerprint: RequestFingerprint
    authority_family: OperationLookupAuthorityFamily | None
    action_id: ActionId | None
    recorded_at: datetime
    retention_days: int | None
    retention_policy_version: str | None
