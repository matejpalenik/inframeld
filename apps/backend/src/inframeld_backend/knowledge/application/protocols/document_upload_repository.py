from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.knowledge.application.dtos.document_upload_record_dto import (
    DocumentUploadRecordDTO,
)
from inframeld_backend.knowledge.application.dtos.document_upload_result_dto import (
    DocumentUploadResultDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO


class DocumentUploadRepository(Protocol):
    @abstractmethod
    async def reserve(
        self, *, scope: ArtifactScopeDTO, actor: PrincipalId, command: UploadDocumentCommand
    ) -> DocumentUploadRecordDTO:
        """Recover the exact original first or reserve one new Document and artifact slot."""
        ...

    @abstractmethod
    async def read_original(
        self, *, scope: ArtifactScopeDTO, actor: PrincipalId, command: UploadDocumentCommand
    ) -> DocumentUploadRecordDTO:
        """Read under the caller's current authorized admission turn."""
        ...

    @abstractmethod
    async def admit(
        self, *, record: DocumentUploadRecordDTO, verified: VerifiedArtifactDTO
    ) -> DocumentUploadResultDTO:
        """Publish the verified original and commit the immutable version and audit together."""
        ...

    @abstractmethod
    async def decline(self, *, record: DocumentUploadRecordDTO) -> None:
        """Release only a provably unused Document slot, retaining the original storage."""
        ...
