from dataclasses import dataclass, field
from uuid import UUID

from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.enums.restored_job_quarantine_intent import (
    RestoredJobQuarantineIntent,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class RestoredJobQuarantineCommand(Command):
    """Bind protected restore maintenance to the exact original job and reviewed state."""

    operation_id: OperationId
    expected_installation_id: InstallationId
    job_id: JobId
    job_operation_id: OperationId
    intent: RestoredJobQuarantineIntent
    expected_status: JobStatus | None = None
    expected_attempt: int | None = None
    operator_label: str | None = field(default=None, repr=False)
    reason: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._require_text(self.job_operation_id.value, 128)
        if str(UUID(self.operation_id.value)) != self.operation_id.value:
            raise ValueError("The maintenance operation identity must be a canonical UUID.")
        if self.operation_id == self.job_operation_id:
            raise ValueError("Maintenance and original operation identities must differ.")

        if self.intent is RestoredJobQuarantineIntent.INSPECT:
            if any(
                value is not None
                for value in (
                    self.expected_status,
                    self.expected_attempt,
                    self.operator_label,
                    self.reason,
                )
            ):
                raise ValueError("Inspection does not accept mutation inputs.")
        elif self.intent is RestoredJobQuarantineIntent.QUARANTINE:
            if (
                self.expected_status not in (JobStatus.QUEUED, JobStatus.RUNNING)
                or type(self.expected_attempt) is not int
                or not 0 <= self.expected_attempt <= 3
            ):
                raise ValueError("Quarantine requires the reviewed status and attempt.")
            self._require_text(self.operator_label, 128)
            self._require_text(self.reason, 512)
        else:
            raise ValueError("Unsupported restored job maintenance intent.")

    @staticmethod
    def _require_text(value: str | None, limit: int) -> None:
        if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
            raise ValueError("Maintenance text must be nonblank and bounded.")
        value.encode("utf-8")
