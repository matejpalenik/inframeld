from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class ProjectUploadAudienceDTO:
    """Supply saved state to a trusted admission owner, never an authorization result."""

    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    audience: UploadAudience | None

    def __post_init__(self) -> None:
        RevisionValidation.require(self.access_revision)
