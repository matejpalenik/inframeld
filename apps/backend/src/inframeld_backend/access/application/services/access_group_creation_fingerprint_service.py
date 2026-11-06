from json import dumps

from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class AccessGroupCreationFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_create(self, command: CreateAccessGroupCommand) -> RequestFingerprint:
        canonical = dumps(
            {
                "projectId": str(command.project_id.value),
                "name": command.name.value,
                "displayName": command.display_name.value,
                "expectedAccessRevision": command.expected_access_revision,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.access-group.create:v1", canonical_request=canonical
        )
