from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO


@dataclass(frozen=True, slots=True)
class SpendingEvidenceResolutionDTO:
    """Retain one pending item's selected proof and its original resolution outcome.

    This processing state belongs to the existing pending evidence record. It
    neither replaces immutable evidence nor changes an earlier financial receipt.
    """

    pending_evidence_id: UUID
    authoritative_evidence_id: UUID
    result: SpendingCallRecordDTO
