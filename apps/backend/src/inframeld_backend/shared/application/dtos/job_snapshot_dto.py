from dataclasses import dataclass, field
from datetime import datetime

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus


@dataclass(frozen=True, slots=True)
class JobSnapshotDTO:
    """Observe durable execution facts without authorizing their use."""

    job_id: JobId
    operation_id: OperationId
    request_id: RequestId
    authority: AdmittedWorkAuthorityDTO
    payload: JobPayload
    status: JobStatus
    admitted_at: datetime
    queued_deadline: datetime
    due_at: datetime
    observed_at: datetime
    attempt: int
    work_deadline: datetime | None
    fence: JobFence | None
    lease_expires_at: datetime | None
    cancel_requested: bool
    pending_effect: str | None
    reason: str | None
    checkpoint: bytes = field(repr=False)
