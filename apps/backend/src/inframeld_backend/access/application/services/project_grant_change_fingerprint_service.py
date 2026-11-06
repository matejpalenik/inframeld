"""Fingerprint the meaningful fields of a project grant command."""

from json import dumps

from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectGrantChangeFingerprintService:
    """Define grant-command meaning before the shared keyed fingerprint is made."""

    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_set(self, command: SetProjectActionGrantCommand) -> RequestFingerprint:
        canonical_request = dumps(
            {
                "actionId": command.action_id.value,
                "canGrant": command.can_grant,
                "expectedAccessRevision": command.expected_access_revision,
                "projectId": str(command.project_id.value),
                "recipientPrincipalId": str(command.recipient_principal_id.value),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.project-grant.set:v1", canonical_request=canonical_request
        )

    def for_remove(self, command: RemoveProjectActionGrantCommand) -> RequestFingerprint:
        canonical_request = dumps(
            {
                "actionId": command.action_id.value,
                "expectedAccessRevision": command.expected_access_revision,
                "projectId": str(command.project_id.value),
                "recipientPrincipalId": str(command.recipient_principal_id.value),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.project-grant.remove:v1", canonical_request=canonical_request
        )
