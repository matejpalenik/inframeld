from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class JobAdmissionDTO:
    job_id: JobId
    operation_id: OperationId
    created: bool
