from json import dumps

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectDeletionFingerprintService:
    """Define stable Project-deletion request meaning using the configured keyed fingerprint."""

    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_delete(self, command: DeleteProjectCommand) -> RequestFingerprint:
        canonical_request = dumps(
            {
                "projectId": str(command.project_id.value),
                "expectedAccessRevision": command.expected_access_revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.project.delete:v1", canonical_request=canonical_request
        )
