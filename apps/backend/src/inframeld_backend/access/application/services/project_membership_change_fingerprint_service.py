import json

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectMembershipChangeFingerprintService:
    def __init__(self, fingerprints: RequestFingerprintService) -> None:
        self._fingerprints = fingerprints

    def for_add(self, command: AddProjectMemberCommand) -> RequestFingerprint:
        return self._fingerprints.fingerprint(
            purpose="access.project-membership.add:v1", canonical_request=self._canonical(command)
        )

    def for_remove(self, command: RemoveProjectMemberCommand) -> RequestFingerprint:
        return self._fingerprints.fingerprint(
            purpose="access.project-membership.remove:v1",
            canonical_request=self._canonical(command),
        )

    @staticmethod
    def _canonical(command: AddProjectMemberCommand | RemoveProjectMemberCommand) -> bytes:
        return json.dumps(
            {
                "projectId": str(command.project_id.value),
                "principalId": str(command.principal_id.value),
                "expectedAccessRevision": command.expected_access_revision,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
