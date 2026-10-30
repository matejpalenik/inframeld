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


@dataclass(frozen=True, slots=True)
class JobAttemptContextDTO:
    """Carry original work and the current fence, never cached permission or a session."""

    job_id: JobId
    operation_id: OperationId
    request_id: RequestId
    authority: AdmittedWorkAuthorityDTO
    payload: JobPayload
    attempt: int
    fence: JobFence
    work_deadline: datetime
    checkpoint: bytes = field(repr=False)
