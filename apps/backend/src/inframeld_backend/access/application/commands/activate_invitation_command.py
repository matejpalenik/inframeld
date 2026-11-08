from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.shared.application.commands.command import Command


@dataclass(frozen=True, slots=True)
class ActivateInvitationCommand(Command):
    token: InvitationToken
