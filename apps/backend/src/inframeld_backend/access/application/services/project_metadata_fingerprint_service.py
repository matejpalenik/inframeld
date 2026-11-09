import json

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectMetadataFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_update(self, command: UpdateProjectMetadataCommand) -> RequestFingerprint:
        return self._request_fingerprint_service.fingerprint(
            purpose="project-metadata-update",
            canonical_request=json.dumps(
                [
                    str(command.project_id.value),
                    command.expected_metadata_revision,
                    None if command.name is None else command.name.value,
                    None if command.display_name is None else command.display_name.value,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
