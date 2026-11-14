from dataclasses import dataclass

from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class ChangeModelConnectionGrantCommand(Command):
    model_connection_id: ModelConnectionId
    recipient_id: PrincipalId
    action: ModelConnectionAction
    expected_access_revision: int
    can_grant: bool | None

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
        if self.can_grant is not None and type(self.can_grant) is not bool:
            raise ValueError("The assignment level must be a boolean.")
