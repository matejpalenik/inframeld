from abc import abstractmethod
from collections.abc import AsyncIterable
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.knowledge.application.dtos.document_upload_result_dto import (
    DocumentUploadResultDTO,
)


class DocumentUploader(Protocol):
    @abstractmethod
    async def upload(
        self,
        *,
        access: AccessContextDTO,
        command: UploadDocumentCommand,
        chunks: AsyncIterable[bytes],
    ) -> DocumentUploadResultDTO:
        """Admit one verified PDF or recover the same original outcome."""
        ...
