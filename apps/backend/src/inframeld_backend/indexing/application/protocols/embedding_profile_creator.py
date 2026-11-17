from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.indexing.application.commands.create_embedding_profile_command import (
    CreateEmbeddingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class EmbeddingProfileCreator(Protocol):
    @abstractmethod
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateEmbeddingProfileCommand,
        context: IdempotencyContextDTO,
    ) -> EmbeddingProfileCreationDTO:
        """Save one immutable definition or return its authorized original receipt."""
        ...
