from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@dataclass(frozen=True, slots=True)
class CreateProjectCommand(Command):
    organization_id: OrganizationId
    expected_access_revision: int
    name: ResourceName
    display_name: SubmittedDisplayName

    def __post_init__(self) -> None:
        if (
            type(self.expected_access_revision) is not int
            or not 0 <= self.expected_access_revision <= RevisionValidation.MAX_VALUE
        ):
            raise ValueError("The Organization access revision must be a nonnegative whole number.")
