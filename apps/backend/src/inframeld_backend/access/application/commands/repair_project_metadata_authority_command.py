from dataclasses import dataclass, field
from uuid import UUID

from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class RepairProjectMetadataAuthorityCommand(Command, ProjectCommand):
    """Request only the exact metadata responsibility through the protected host boundary."""

    expected_installation_id: InstallationId
    operation_id: OperationId
    project_id: ProjectId
    expected_access_revision: int
    expected_identity_id: UUID
    operator_label: str
    reason: str
    identity_proof: HumanAccessTokenCredential = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.expected_identity_id)
        if type(self.expected_access_revision) is not int:
            raise TypeError("The Access revision must be a whole number.")
        if not 0 <= self.expected_access_revision < 2**63:
            raise ValueError("The Access revision is outside its supported range.")
        for value, bound in (
            (self.operation_id.value, 128),
            (self.operator_label, 128),
            (self.reason, 512),
        ):
            ValueValidation.require_string(value)
            if not value.strip() or len(value) > bound or "\x00" in value:
                raise ValueError(
                    "Maintenance attribution and request values must be nonblank and bounded."
                )
            value.encode("utf-8")
