from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class ChangeProcessingProfileGrantCommand(Command):
    processing_profile_id: ProcessingProfileId
    recipient_id: PrincipalId
    action: ProcessingProfileAction
    expected_access_revision: int
    can_grant: bool | None

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
        if self.can_grant is not None and type(self.can_grant) is not bool:
            raise ValueError("The assignment level must be a boolean.")
