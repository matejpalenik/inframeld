from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.current_document_access_dto import (
    CurrentDocumentAccessDTO,
)
from inframeld_backend.access.application.dtos.selected_document_source_dto import (
    SelectedDocumentSourceDTO,
)
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class DocumentAccessAuthorizer(Protocol):
    """Decide source disclosure from trusted refreshed producer observations.

    Query/action permission is separate. A genuine empty selection grants no
    resource authority. Receivers refresh source lifecycle and audience facts at
    each protected boundary, including after coordination waits. Returned pairs
    neither expand the selection nor authorize later disclosure or network work.
    """

    @abstractmethod
    async def permitted_sources(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selected: tuple[SelectedDocumentSourceDTO, ...],
        documents: tuple[CurrentDocumentAccessDTO, ...],
    ) -> tuple[DocumentSourceId, ...]: ...

    @abstractmethod
    async def require_complete_evidence(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selected: tuple[SelectedDocumentSourceDTO, ...],
        documents: tuple[CurrentDocumentAccessDTO, ...],
    ) -> tuple[DocumentSourceId, ...]:
        """Deny the whole bundle without disclosing which source failed."""
        ...
