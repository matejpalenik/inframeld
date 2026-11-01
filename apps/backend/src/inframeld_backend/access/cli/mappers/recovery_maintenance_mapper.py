from datetime import UTC
from uuid import UUID

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)
from inframeld_backend.access.cli.errors.recovery_maintenance_input_error import (
    RecoveryMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.maintenance_input_mapper import MaintenanceInputMapper
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("A string is required.")
    return value


class RecoveryMaintenanceMapper:
    """Map the delivered maintenance mode without retaining submitted JSON."""

    @staticmethod
    def read(payload: bytes) -> ResumeIdentityRecoveryCleanupCommand:
        operation_id = None
        try:
            values = MaintenanceInputMapper.read(payload)
            operation_id = MaintenanceInputMapper.correlation(values)

            if set(values) != {
                "schemaVersion",
                "mode",
                "expectedInstallationId",
                "operationId",
                "recoveryOperationId",
                "operatorLabel",
                "reason",
            }:
                raise ValueError("Invalid fields.")
            if (
                type(values["schemaVersion"]) is not int
                or values["schemaVersion"] != 1
                or values["mode"] != "resume-recovery-cleanup"
            ):
                raise ValueError("Unsupported maintenance request.")

            return ResumeIdentityRecoveryCleanupCommand(
                InstallationId(UUID(_text(values["expectedInstallationId"]))),
                OperationId(_text(values["operationId"])),
                OperationId(_text(values["recoveryOperationId"])),
                _text(values["operatorLabel"]),
                _text(values["reason"]),
            )
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise RecoveryMaintenanceInputError(operation_id) from None

    @staticmethod
    def result(result: IdentityRecoveryCleanupResumeResultDTO) -> dict[str, object]:
        response: dict[str, object] = {
            "schemaVersion": 1,
            "mode": "resume-recovery-cleanup",
            "operationId": result.operation_id.value,
            "installationId": str(result.installation_id.value),
            "recoveryOperationId": result.recovery_operation_id.value,
            "outcome": result.outcome.value,
            "released": result.released,
        }
        if result.run_id is not None:
            if result.deadline is None:
                raise RuntimeError("An authorized run requires its deadline.")
            response["runId"] = str(result.run_id)
            response["deadline"] = (
                result.deadline.astimezone(UTC).isoformat().replace("+00:00", "Z")
            )

        return response
