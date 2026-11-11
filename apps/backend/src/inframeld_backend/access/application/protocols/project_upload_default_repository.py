from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_upload_default_record_dto import (
    ProjectUploadDefaultRecordDTO,
)
from inframeld_backend.access.domain.entities.project_upload_default import ProjectUploadDefault
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectUploadDefaultRepository(Protocol):
    @abstractmethod
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectUploadDefault:
        """Load the exact default in the caller's coordinated transaction."""
        ...

    @abstractmethod
    async def save(
        self,
        default: ProjectUploadDefault,
        *,
        original: ProjectUploadDefaultRecordDTO,
        fingerprint: RequestFingerprint,
    ) -> None:
        """Persist the checked set, one changed revision/audit and immutable original atomically.

        Guard exact reservation scope, PUT route/fingerprint and before snapshot.
        A no-op saves only its original. Service owns shared reservation completion.
        Never commit, retry, or retain foreign keys from history to removable groups.
        """
        ...

    @abstractmethod
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectUploadDefaultRecordDTO | None:
        """Read only an authentic, scoped, unexpired safe original under current authority."""
        ...
