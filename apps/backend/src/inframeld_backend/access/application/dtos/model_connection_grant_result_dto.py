from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ModelConnectionGrantResultDTO:
    target: ModelConnectionGrantTargetDTO
    recipient_id: PrincipalId
    action: ModelConnectionAction
    can_grant: bool | None
    access_revision: int
    changed: bool
    status_code: Literal[200, 201]
    operation: CompletedSynchronousOperationDTO
