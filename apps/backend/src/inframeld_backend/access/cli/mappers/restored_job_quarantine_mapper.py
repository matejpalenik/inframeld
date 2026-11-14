from uuid import UUID

from inframeld_backend.shared.application.commands.restored_job_quarantine_command import (
    RestoredJobQuarantineCommand,
)
from inframeld_backend.shared.application.dtos.restored_job_quarantine_result_dto import (
    RestoredJobQuarantineResultDTO,
)
from inframeld_backend.shared.application.enums.restored_job_quarantine_intent import (
    RestoredJobQuarantineIntent as Intent,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("A string is required.")
    return value


class RestoredJobQuarantineMapper:
    @staticmethod
    def result(
        command: RestoredJobQuarantineCommand, result: RestoredJobQuarantineResultDTO
    ) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "mode": "quarantine-restored-job",
            "intent": command.intent.value,
            "operationId": command.operation_id.value,
            "installationId": str(command.expected_installation_id.value),
            "jobId": str(command.job_id.value),
            "jobOperationId": command.job_operation_id.value,
            "status": result.status.value,
            "attempt": result.attempt,
            "eligible": result.eligible,
        }

    @staticmethod
    def read(values: dict[str, object]) -> RestoredJobQuarantineCommand:
        if type(values.get("schemaVersion")) is not int or values["schemaVersion"] != 1:
            raise ValueError("Unsupported maintenance request.")
        intent = Intent(_text(values.get("intent")))
        fields = {
            "schemaVersion",
            "mode",
            "intent",
            "expectedInstallationId",
            "operationId",
            "jobId",
            "jobOperationId",
        }
        quarantine = intent is Intent.QUARANTINE
        if quarantine:
            fields.update(("expectedStatus", "expectedAttempt", "operatorLabel", "reason"))
        if values.keys() != fields:
            raise ValueError("Invalid maintenance fields.")

        attempt = values.get("expectedAttempt")
        if quarantine and type(attempt) is not int:
            raise ValueError("Expected attempt must be an integer.")
        return RestoredJobQuarantineCommand(
            operation_id=OperationId(str(UUID(_text(values["operationId"])))),
            expected_installation_id=InstallationId(UUID(_text(values["expectedInstallationId"]))),
            job_id=JobId(UUID(_text(values["jobId"]))),
            job_operation_id=OperationId(_text(values["jobOperationId"])),
            intent=intent,
            expected_status=JobStatus(_text(values["expectedStatus"])) if quarantine else None,
            expected_attempt=attempt if type(attempt) is int else None,
            operator_label=_text(values["operatorLabel"]) if quarantine else None,
            reason=_text(values["reason"]) if quarantine else None,
        )
