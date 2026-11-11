from inframeld_backend.access.domain.errors.project_upload_default_errors import (
    ProjectUploadDefaultStaleRevisionError,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectUploadDefault:
    """Own a future audience independently of any Document or version."""

    def __init__(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        audience: UploadAudience | None,
        access_revision: int,
    ) -> None:
        RevisionValidation.require(access_revision)
        self._organization_id = organization_id
        self._project_id = project_id
        self._audience = audience
        self._access_revision: int = access_revision

    @property
    def organization_id(self) -> OrganizationId:
        return self._organization_id

    @property
    def project_id(self) -> ProjectId:
        return self._project_id

    @property
    def audience(self) -> UploadAudience | None:
        return self._audience

    @property
    def access_revision(self) -> int:
        return self._access_revision

    def replace(self, *, audience: UploadAudience, expected_access_revision: int) -> bool:
        RevisionValidation.require(expected_access_revision)
        if expected_access_revision != self._access_revision:
            raise ProjectUploadDefaultStaleRevisionError()
        if self._audience == audience:
            return False
        if self._access_revision == RevisionValidation.MAX_VALUE:
            raise InvalidStateTransitionError("The Project Access revision cannot advance.")

        self._audience = audience
        self._access_revision += 1
        return True
