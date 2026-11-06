from dataclasses import dataclass

from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class ChangeAccessGroupRelationshipCommand(Command, ProjectCommand):
    project_id: ProjectId
    group_id: AccessGroupId
    principal_id: PrincipalId
    expected_access_revision: int
    change_kind: AccessGroupChangeKind

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
