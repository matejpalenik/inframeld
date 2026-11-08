import json
from dataclasses import asdict
from uuid import UUID

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.commands.revoke_invitation_command import (
    RevokeInvitationCommand,
)
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class InvitationFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_issue(self, command: IssueInvitationCommand) -> RequestFingerprint:
        """Bind the validated requested meaning, including omitted versus explicit lifetime."""
        return self._request_fingerprint_service.fingerprint(
            purpose="access.invitation.issue:v1",
            canonical_request=json.dumps(
                asdict(command), default=self._uuid_json, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
        )

    @staticmethod
    def _uuid_json(value: object) -> str:
        if isinstance(value, UUID):
            return str(value)
        raise TypeError("The invitation request has an unsupported fingerprint value.")

    def for_revoke(self, command: RevokeInvitationCommand) -> RequestFingerprint:
        return self._request_fingerprint_service.fingerprint(
            purpose="access.invitation.revoke:v1",
            canonical_request=json.dumps(
                asdict(command), default=self._uuid_json, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
        )

    def for_activation(
        self, command: ActivateInvitationCommand, *, invitation_id: InvitationId
    ) -> RequestFingerprint:
        return self._request_fingerprint_service.fingerprint(
            purpose="access.invitation.activate:v1",
            canonical_request=json.dumps(
                {
                    "invitationId": str(invitation_id.value),
                    "tokenDigest": command.token.digest().value.hex(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
