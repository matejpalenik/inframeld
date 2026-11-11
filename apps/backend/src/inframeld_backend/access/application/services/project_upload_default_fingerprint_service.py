from json import dumps

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectUploadDefaultFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_set(self, command: SetProjectUploadDefaultCommand) -> RequestFingerprint:
        canonical = dumps(
            {
                "projectId": str(command.project_id.value),
                "groupIds": [str(group.value) for group in command.audience.group_ids],
                "expectedAccessRevision": command.expected_access_revision,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.project-upload-default.set:v1", canonical_request=canonical
        )
