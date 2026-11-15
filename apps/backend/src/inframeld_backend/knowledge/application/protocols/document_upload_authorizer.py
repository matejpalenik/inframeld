from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO


class DocumentUploadAuthorizer(Protocol):
    @abstractmethod
    async def require_current(
        self, *, access: AccessContextDTO, command: UploadDocumentCommand
    ) -> ArtifactScopeDTO:
        """Take the Organization and Project turns and require exact Add on every group."""
        ...
