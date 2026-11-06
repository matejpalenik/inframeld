from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class RemoveOrganizationActionGrantCommand(Command):
    """Request removal of only one exact Organization assignment."""

    organization_id: OrganizationId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    expected_access_revision: int

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
