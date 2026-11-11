from json import dumps

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ApplicationAccountDeletionFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_delete(self, command: DeleteApplicationAccountCommand) -> RequestFingerprint:
        canonical = dumps(
            {
                "projectId": str(command.project_id.value),
                "applicationPrincipalId": str(command.application_principal_id.value),
                "expectedAccessRevision": command.expected_access_revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.application-account.delete:v1", canonical_request=canonical
        )
