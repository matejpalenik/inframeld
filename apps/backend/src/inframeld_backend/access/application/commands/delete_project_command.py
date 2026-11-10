from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class DeleteProjectCommand(Command, ProjectCommand):
    project_id: ProjectId
    expected_access_revision: int

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
