import json

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectMetadataFingerprintService:
    def __init__(self, fingerprints: RequestFingerprintService) -> None:
        self._fingerprints = fingerprints

    def for_update(self, command: UpdateProjectMetadataCommand) -> RequestFingerprint:
        return self._fingerprints.fingerprint(
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

    def for_repair(
        self, command: "RepairProjectMetadataAuthorityCommand", identity: "VerifiedHumanIdentityDTO"
    ) -> RequestFingerprint:
        return self._fingerprints.fingerprint(
            purpose="project-metadata-repair",
            canonical_request=json.dumps(
                [
                    "repair-stranded-authority",
                    str(command.expected_installation_id.value),
                    identity.authority.value,
                    identity.subject.value,
                    str(command.expected_identity_id),
                    str(command.project_id.value),
                    command.expected_access_revision,
                    command.operator_label,
                    command.reason,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
