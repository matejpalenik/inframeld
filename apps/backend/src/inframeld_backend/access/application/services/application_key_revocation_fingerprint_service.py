from json import dumps

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ApplicationKeyRevocationFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_revoke(self, command: RevokeApplicationKeyCommand) -> RequestFingerprint:
        canonical = dumps(
            {
                "projectId": str(command.project_id.value),
                "applicationPrincipalId": str(command.application_principal_id.value),
                "keyId": str(command.key_id.value),
                "expectedAccessRevision": command.expected_access_revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.application-key.revoke:v1", canonical_request=canonical
        )
