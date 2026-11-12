from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanSuspensionJobBindingDTO:
    """Retain exact Organization-only cleanup work without certifying dispatch."""

    obligation_id: HumanSuspensionId
    job_id: JobId
    operation_id: OperationId
    request_id: RequestId
    installation_id: InstallationId
    organization_id: UUID
    principal_id: UUID
    initiator_principal_id: UUID
    identity: VerifiedHumanIdentityDTO
    key: IdempotencyKey
    fingerprint: RequestFingerprint
    before_access_revision: int
    access_revision: int
