from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


@dataclass(frozen=True, slots=True)
class StrandedAuthorityRepairReceiptDTO:
    """Retain safe original meaning and outcome, never the replaceable proof token."""

    fingerprint: RequestFingerprint
    identity: VerifiedHumanIdentityDTO
    expected_identity_id: UUID
    operator_label: str
    reason: str
    before_revision: int
    authorized_at: datetime
    result: StrandedAuthorityRepairResultDTO
