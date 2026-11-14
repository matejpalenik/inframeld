from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.indexing.application.commands.create_processing_profile_command import (
    CreateProcessingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ProcessingProfileCreator(Protocol):
    """Create or replay a profile under current authority and return after commit."""

    @abstractmethod
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProcessingProfileCommand,
        context: IdempotencyContextDTO,
    ) -> ProcessingProfileCreationDTO: ...
