from uuid import UUID

from inframeld_backend.access.application.commands.human_suspension_cleanup_maintenance_command import (
    HumanSuspensionCleanupMaintenanceCommand,
)
from inframeld_backend.access.application.dtos.human_suspension_cleanup_maintenance_result_dto import (
    HumanSuspensionCleanupMaintenanceResultDTO,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_execution_state import (
    HumanSuspensionCleanupExecutionState,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_intent import (
    HumanSuspensionCleanupMaintenanceIntent as Intent,
)
from inframeld_backend.access.cli.mappers.maintenance_input_mapper import MaintenanceInputMapper
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("A string is required.")
    return value


class HumanSuspensionCleanupMaintenanceMapper:
    @staticmethod
    def read(payload: bytes) -> HumanSuspensionCleanupMaintenanceCommand:
        values = MaintenanceInputMapper.read(payload)
        if (
            type(values.get("schemaVersion")) is not int
            or values["schemaVersion"] != 1
            or values.get("mode") != "human-suspension-cleanup"
        ):
            raise ValueError("Unsupported maintenance request.")
        intent = Intent(_text(values.get("intent")))
        fields = {
            "schemaVersion",
            "mode",
            "intent",
            "expectedInstallationId",
            "operationId",
            "cleanupOperationId",
        }
        if intent is Intent.CONTINUE:
            fields.update(("operatorLabel", "reason"))
        if values.keys() != fields:
            raise ValueError("Invalid fields.")

        return HumanSuspensionCleanupMaintenanceCommand(
            InstallationId(UUID(_text(values["expectedInstallationId"]))),
            OperationId(_text(values["operationId"])),
            OperationId(_text(values["cleanupOperationId"])),
            intent,
            operator_label=_text(values["operatorLabel"]) if intent is Intent.CONTINUE else None,
            reason=_text(values["reason"]) if intent is Intent.CONTINUE else None,
        )

    @staticmethod
    def result(result: HumanSuspensionCleanupMaintenanceResultDTO) -> dict[str, object]:
        response: dict[str, object] = {
            "schemaVersion": 1,
            "mode": "human-suspension-cleanup",
            "operationId": result.operation_id.value,
            "installationId": str(result.installation_id.value),
            "cleanupOperationId": result.cleanup_operation_id.value,
        }
        if isinstance(result.outcome, HumanSuspensionCleanupExecutionState):
            kratos, grants, logins = (
                result.kratos_sessions,
                result.hydra_cli_grants,
                result.hydra_remembered_logins,
            )
            if kratos is None or grants is None or logins is None:
                raise RuntimeError("Inspection requires all three cleanup states.")
            response.update(
                intent=Intent.INSPECT.value,
                execution=result.outcome.value,
                steps={
                    "kratosSessions": kratos.value,
                    "hydraCliGrants": grants.value,
                    "hydraRememberedLogins": logins.value,
                },
            )
        else:
            response.update(intent=Intent.CONTINUE.value, outcome=result.outcome.value)
        return response
