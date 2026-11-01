from uuid import UUID

from pydantic import TypeAdapter

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_result_dto import (
    ProjectMetadataRepairResultDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.cli.errors.project_metadata_maintenance_input_error import (
    ProjectMetadataMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.maintenance_input_mapper import MaintenanceInputMapper
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("A string is required.")
    return value


class ProjectMetadataMaintenanceMapper:
    @staticmethod
    def read(payload: bytes) -> RepairProjectMetadataAuthorityCommand:
        operation_id = None
        try:
            values = MaintenanceInputMapper.read(payload)
            operation_id = MaintenanceInputMapper.correlation(values)
            if set(values) != {
                "schemaVersion",
                "mode",
                "expectedInstallationId",
                "operationId",
                "operatorLabel",
                "reason",
                "expectedAccessRevision",
                "expectedIdentityId",
                "identityProof",
                "responsibility",
            }:
                raise ValueError("Invalid maintenance fields.")
            if (
                type(values["schemaVersion"]) is not int
                or values["schemaVersion"] != 1
                or values["mode"] != "repair-stranded-authority"
            ):
                raise ValueError("Unsupported maintenance request.")
            responsibility = TypeAdapter(dict[str, object]).validate_python(
                values["responsibility"], strict=True
            )
            if (
                set(responsibility) != {"kind", "target", "actionId"}
                or responsibility["kind"] != "action-grantor"
                or responsibility["actionId"] != "edit-project-metadata"
            ):
                raise ValueError("Unsupported repair responsibility.")
            target = TypeAdapter(dict[str, object]).validate_python(
                responsibility["target"], strict=True
            )
            if set(target) != {"kind", "projectId"} or target["kind"] != "project":
                raise ValueError("Unsupported repair target.")
            proof = TypeAdapter(dict[str, object]).validate_python(
                values["identityProof"], strict=True
            )
            if set(proof) != {"kind", "accessToken"} or proof["kind"] != "hydra-access-token":
                raise ValueError("Unsupported recipient proof.")
            revision = values["expectedAccessRevision"]
            if type(revision) is not int:
                raise ValueError("A whole-number review revision is required.")
            return RepairProjectMetadataAuthorityCommand(
                InstallationId(UUID(_text(values["expectedInstallationId"]))),
                OperationId(_text(values["operationId"])),
                ProjectId(UUID(_text(target["projectId"]))),
                revision,
                UUID(_text(values["expectedIdentityId"])),
                _text(values["operatorLabel"]),
                _text(values["reason"]),
                HumanAccessTokenCredential(_text(proof["accessToken"])),
            )
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ProjectMetadataMaintenanceInputError(operation_id) from None

    @staticmethod
    def result(result: ProjectMetadataRepairResultDTO) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "mode": "repair-stranded-authority",
            "operationId": result.operation_id.value,
            "installationId": str(result.installation_id.value),
            "principalId": str(result.recipient_id.value),
            "accessRevision": result.access_revision,
            "outcome": "repaired",
            "responsibility": {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(result.project_id.value)},
                "actionId": "edit-project-metadata",
            },
        }
