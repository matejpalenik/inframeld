import json

from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectCreationFingerprintService:
    def __init__(self, fingerprints: RequestFingerprintService) -> None:
        self._fingerprints = fingerprints

    def for_create(self, command: CreateProjectCommand) -> RequestFingerprint:
        return self._fingerprints.fingerprint(
            purpose="project-creation",
            canonical_request=json.dumps(
                [
                    str(command.organization_id.value),
                    command.expected_access_revision,
                    command.name.value,
                    command.display_name.value,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
