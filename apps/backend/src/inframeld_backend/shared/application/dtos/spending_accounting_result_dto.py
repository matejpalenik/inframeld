from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO


@dataclass(frozen=True, slots=True)
class SpendingAccountingResultDTO:
    """Report a new, recovered or pending accounting result, never dispatch authority."""

    record: SpendingCallRecordDTO
    recovered: bool = False
    pending: bool = False
