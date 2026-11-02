from uuid import UUID

from pydantic import TypeAdapter

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_result_dto import (
    FirstAdministratorBootstrapResultDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.cli.errors.project_metadata_maintenance_input_error import (
    ProjectMetadataMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.maintenance_input_mapper import MaintenanceInputMapper
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("A string is required.")
    return value


class FirstAdministratorBootstrapMapper:
    @staticmethod
    def read(payload: bytes) -> BootstrapFirstAdministratorCommand:
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
            }:
                raise ValueError("Invalid bootstrap fields.")
            if (
                type(values["schemaVersion"]) is not int
                or values["schemaVersion"] != 1
                or values["mode"] != "bootstrap-first-administrator"
            ):
                raise ValueError("Unsupported maintenance request.")
            proof = TypeAdapter(dict[str, object]).validate_python(
                values["identityProof"], strict=True
            )
            if set(proof) != {"kind", "accessToken"} or proof["kind"] != "hydra-access-token":
                raise ValueError("Unsupported recipient proof.")
            revision = values["expectedAccessRevision"]
            if type(revision) is not int:
                raise ValueError("A whole-number review revision is required.")
            return BootstrapFirstAdministratorCommand(
                InstallationId(UUID(_text(values["expectedInstallationId"]))),
                OperationId(_text(values["operationId"])),
                revision,
                UUID(_text(values["expectedIdentityId"])),
                _text(values["operatorLabel"]),
                _text(values["reason"]),
                HumanAccessTokenCredential(_text(proof["accessToken"])),
            )
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ProjectMetadataMaintenanceInputError(operation_id) from None

    @staticmethod
    def result(result: FirstAdministratorBootstrapResultDTO) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "mode": "bootstrap-first-administrator",
            "operationId": result.operation_id.value,
            "installationId": str(result.installation_id.value),
            "principalId": str(result.recipient_id.value),
            "accessRevision": result.access_revision,
            "outcome": "bootstrapped",
        }
