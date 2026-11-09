from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_upload_audience_dto import (
    ProjectUploadAudienceDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectUploadAudienceReader(Protocol):
    """Supply real saved audience facts independently of default-administration authority."""

    @abstractmethod
    async def read_upload_audience(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectUploadAudienceDTO:
        """Use the caller's active READ COMMITTED transaction and ordered short locks.

        Fail on missing/foreign Project or unavailable/incoherent facts. Only a
        valid Project with zero saved links is unconfigured. The admission owner
        checks current actor/credential eligibility and Add on every returned
        group before retaining an audience. This observation grants no authority
        and must be refreshed after waits. Do not commit or call a provider.
        """
        ...
