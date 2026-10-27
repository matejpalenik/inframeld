"""Fingerprint the meaningful fields of a project grant command."""

from json import dumps

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)

_ASSIGN_USE_ONLY_PURPOSE = "access.project-grant.assign-use-only:v1"


class ProjectGrantChangeFingerprintService:
    """Define grant-command meaning before the shared keyed fingerprint is made."""

    def __init__(self, fingerprints: RequestFingerprintService) -> None:
        self._fingerprints = fingerprints

    def for_assign_use_only(self, command: AssignProjectUseOnlyGrantCommand) -> RequestFingerprint:
        """Retain the canonical request bytes used by existing reservations."""
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
        return self._fingerprints.fingerprint(
            purpose=_ASSIGN_USE_ONLY_PURPOSE, canonical_request=canonical_request
        )
