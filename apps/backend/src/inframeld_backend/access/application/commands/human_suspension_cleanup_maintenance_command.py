from dataclasses import dataclass

from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_intent import (
    HumanSuspensionCleanupMaintenanceIntent,
)
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanSuspensionCleanupMaintenanceCommand(Command):
    """Identify a retained suspension cleanup through protected host maintenance."""

    expected_installation_id: InstallationId
    operation_id: OperationId
    cleanup_operation_id: OperationId
    intent: HumanSuspensionCleanupMaintenanceIntent
    operator_label: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        self._validate_text(self.operation_id.value, 128)
        self._validate_text(self.cleanup_operation_id.value)
        if self.intent is HumanSuspensionCleanupMaintenanceIntent.INSPECT:
            if self.operator_label is not None or self.reason is not None:
                raise ValueError("Inspection does not accept operator attribution.")
        elif self.intent is HumanSuspensionCleanupMaintenanceIntent.CONTINUE:
            self._validate_text(self.operator_label, 128)
            self._validate_text(self.reason, 512)
        else:
            raise ValueError("The suspension cleanup intent is unsupported.")

    @staticmethod
    def _validate_text(value: str | None, limit: int | None = None) -> None:
        if (
            not isinstance(value, str)
            or not value.strip()
            or "\x00" in value
            or (limit is not None and len(value) > limit)
        ):
            raise ValueError("Maintenance text must be nonblank and bounded.")
        value.encode("utf-8")
