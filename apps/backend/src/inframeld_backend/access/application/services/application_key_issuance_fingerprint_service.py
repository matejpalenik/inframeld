from json import dumps

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ApplicationKeyIssuanceFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_issue(self, command: IssueApplicationKeyCommand) -> RequestFingerprint:
        payload: dict[str, object] = {
            "projectId": str(command.project_id.value),
            "applicationPrincipalId": str(command.application_principal_id.value),
            "allowedAdapters": [adapter.value for adapter in command.allowed_adapters],
            "expectedAccessRevision": command.expected_access_revision,
        }
        if command.expires_in_seconds is not None:
            payload["expiresInSeconds"] = command.expires_in_seconds
        canonical = dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.application-key.issue:v1", canonical_request=canonical
        )
