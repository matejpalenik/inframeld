from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class RevokeInvitationCommand(Command):
    invitation_id: InvitationId
    expected_access_revision: int

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
