from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand


@dataclass(frozen=True, slots=True)
class AssignProjectUseOnlyGrantCommand(Command, ProjectCommand):
    """Request a grant change - current authority and revision require fresh checks."""

    project_id: ProjectId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    expected_access_revision: int

    def __post_init__(self) -> None:
        if type(self.expected_access_revision) is not int:
            raise TypeError("The expected access revision must be a whole number.")
        if self.expected_access_revision < 0:
            raise ValueError("The expected access revision cannot be negative.")
