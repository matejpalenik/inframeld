from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.access.application.dtos.first_administrator_bootstrap_result_dto import (
    FirstAdministratorBootstrapResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


@dataclass(frozen=True, slots=True)
class FirstAdministratorBootstrapReceiptDTO:
    """Retain original request meaning and safe outcome without replaceable proof."""

    fingerprint: RequestFingerprint
    identity: VerifiedHumanIdentityDTO
    expected_identity_id: UUID
    operator_label: str
    reason: str
    before_revision: int
    authorized_at: datetime
    result: FirstAdministratorBootstrapResultDTO
