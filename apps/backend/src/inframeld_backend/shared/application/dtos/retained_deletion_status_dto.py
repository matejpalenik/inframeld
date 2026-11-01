from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.enums.job_status import JobStatus


@dataclass(frozen=True, slots=True)
class RetainedDeletionStatusDTO:
    """Expose only permitted content-free observations, not deletion success by inference."""

    operation_id: OperationId
    job_status: JobStatus | None
    admission_confirmed: bool | None
    access_blocked: bool | None
    application_shutdown_complete: bool | None
    physical_cleanup_complete: bool | None
    expires_at: datetime | None
