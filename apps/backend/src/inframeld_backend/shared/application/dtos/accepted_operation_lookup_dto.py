from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class AcceptedOperationLookupDTO:
    """Report original admission and optional correlation, never current execution or permission."""

    operation_id: OperationId
    expires_at: datetime | None
    job_id: JobId | None = None
