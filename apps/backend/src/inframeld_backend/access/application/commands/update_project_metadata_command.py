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
class UpdateProjectMetadataCommand(Command, ProjectCommand):
    project_id: ProjectId
    expected_metadata_revision: int
    name: ResourceName | None = None
    display_name: SubmittedDisplayName | None = None

    def __post_init__(self) -> None:
        if type(self.expected_metadata_revision) is not int:
            raise TypeError("The metadata revision must be a whole number.")
        if not 0 <= self.expected_metadata_revision <= RevisionValidation.MAX_VALUE:
            raise ValueError("The metadata revision is outside its supported range.")
        if self.name is None and self.display_name is None:
            raise ValueError("At least one replacement field is required.")
