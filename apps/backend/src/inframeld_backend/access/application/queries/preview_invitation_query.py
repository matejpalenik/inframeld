from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken


@dataclass(frozen=True, slots=True)
class PreviewInvitationQuery:
    token: InvitationToken
