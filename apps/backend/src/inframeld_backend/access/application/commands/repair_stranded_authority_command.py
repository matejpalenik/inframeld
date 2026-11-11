from dataclasses import dataclass, field
from uuid import UUID

from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class RepairStrandedAuthorityCommand(Command):
    expected_installation_id: InstallationId
    operation_id: OperationId
    responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO
    expected_access_revision: int
    expected_identity_id: UUID
    operator_label: str
    reason: str
    identity_proof: HumanAccessTokenCredential = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.expected_identity_id)
        RevisionValidation.require(self.expected_access_revision)
        for value, bound in (
            (self.operation_id.value, 128),
            (self.operator_label, 128),
            (self.reason, 512),
        ):
            ValueValidation.require_string(value)
            if not value.strip() or len(value) > bound or "\x00" in value:
                raise ValueError("Maintenance attribution must be nonblank and bounded.")
            value.encode("utf-8")
