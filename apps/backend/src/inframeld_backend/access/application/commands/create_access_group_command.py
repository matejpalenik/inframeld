from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@dataclass(frozen=True, slots=True)
class CreateAccessGroupCommand(Command, ProjectCommand):
    """Request a separate identity without copying the creator's permissions."""

    project_id: ProjectId
    expected_access_revision: int
    name: ResourceName
    display_name: SubmittedDisplayName

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
