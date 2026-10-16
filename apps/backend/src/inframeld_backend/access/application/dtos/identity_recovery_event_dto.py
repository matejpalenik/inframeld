from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)


@dataclass(frozen=True, slots=True)
class IdentityRecoveryEventDTO:
    """Carry a verified callback binding. Constructing this DTO does not verify evidence."""

    flow_id: IdentityRecoveryFlowId
    identity: VerifiedHumanIdentityDTO
    event_kind: IdentityRecoveryEventKind
