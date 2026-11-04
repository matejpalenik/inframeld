from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class AdmitHumanCommand(Command):
    """Request local admission for an exact configured-provider identity."""

    organization_id: OrganizationId
    identity_id: UUID
    expected_access_revision: int

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.identity_id)
        if type(self.expected_access_revision) is not int:
            raise TypeError("The expected access revision must be a whole number.")
        if not 0 <= self.expected_access_revision <= 2**63 - 1:
            raise ValueError("The expected access revision is outside its supported range.")
