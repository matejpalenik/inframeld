from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class IdentityRecoverySessionBindingDTO:
    identity: VerifiedHumanIdentityDTO
    session_id: IdentitySessionId
    operation_id: OperationId
