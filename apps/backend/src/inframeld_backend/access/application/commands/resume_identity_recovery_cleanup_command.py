from dataclasses import dataclass

from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ResumeIdentityRecoveryCleanupCommand(Command):
    """Request another cleanup run through protected host maintenance."""

    expected_installation_id: InstallationId
    operation_id: OperationId
    recovery_operation_id: OperationId
    operator_label: str
    reason: str

    def __post_init__(self) -> None:
        for value, limit in (
            (self.operation_id.value, 128),
            (self.recovery_operation_id.value, None),
            (self.operator_label, 128),
            (self.reason, 512),
        ):
            ValueValidation.require_string(value)
            value.encode("utf-8")
            if not value.strip() or "\x00" in value or (limit is not None and len(value) > limit):
                raise ValueError("Maintenance attribution must be nonblank and bounded.")
