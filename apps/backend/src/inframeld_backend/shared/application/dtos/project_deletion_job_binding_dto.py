from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectDeletionJobBindingDTO:
    """Keep the exact original deletion meaning, without certifying admission or a live fence.

    UUID references retain their named meaning at this Shared supporting-record
    boundary. Access converts its nominal IDs without importing its workflows here.
    """

    obligation_id: UUID
    operation_id: OperationId
    request_id: RequestId
    installation_id: InstallationId
    organization_id: UUID
    project_id: UUID
    initiator_principal_id: UUID
    key: IdempotencyKey
    fingerprint: RequestFingerprint
    before_access_revision: int
    access_revision: int
