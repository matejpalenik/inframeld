from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId


@dataclass(frozen=True, slots=True)
class OriginalOperationLookupRecordDTO:
    """Observe retained operation metadata and an independently established job reference."""

    operation: OperationReservationResultDTO
    job_id: JobId | None = None
