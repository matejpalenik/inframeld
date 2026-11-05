from typing import override

from inframeld_backend.access.domain.errors.project_metadata_errors import (
    ProjectMetadataStaleRevisionError,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class ProjectMetadata:
    """Own mutable naming metadata while preserving permanent identity and legacy labels."""

    def __init__(
        self,
        *,
        project_id: ProjectId,
        organization_id: OrganizationId,
        name: ResourceName | None,
        display_name: str,
        revision: int,
    ) -> None:
        self._project_id = project_id
        self._organization_id = organization_id
        self._name = name
        self._display_name = display_name
        RevisionValidation.require(revision)
        self._revision: int = revision

    @property
    def project_id(self) -> ProjectId:
        return self._project_id

    @property
    def organization_id(self) -> OrganizationId:
        return self._organization_id

    @property
    def name(self) -> ResourceName | None:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def revision(self) -> int:
        return self._revision

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectMetadata):
            return NotImplemented
        return self.project_id == other.project_id

    @override
    def __hash__(self) -> int:
        return hash(self.project_id)

    def change(
        self,
        *,
        expected_revision: int,
        name: ResourceName | None,
        display_name: SubmittedDisplayName | None,
    ) -> bool:
        RevisionValidation.require(expected_revision)
        if expected_revision != self._revision:
            raise ProjectMetadataStaleRevisionError()

        selected_name = self._name if name is None else name
        selected_label = self._display_name if display_name is None else display_name.value
        changed = (selected_name, selected_label) != (self._name, self._display_name)
        if changed:
            if self._revision == RevisionValidation.MAX_VALUE:
                raise InvalidStateTransitionError("The metadata revision cannot advance.")
            self._name = selected_name
            self._display_name = selected_label
            self._revision += 1
        return changed
