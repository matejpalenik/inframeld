from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.access.application.value_objects.identity_settings_flow_id import (
    IdentitySettingsFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class IdentityRecoverySettingsBindingDTO:
    identity: VerifiedHumanIdentityDTO
    settings_flow_id: IdentitySettingsFlowId
    session_id: IdentitySessionId
    operation_id: OperationId
    source_recovery_flow_id: IdentityRecoveryFlowId | None
