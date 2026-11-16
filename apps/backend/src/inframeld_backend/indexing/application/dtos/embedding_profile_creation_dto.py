from dataclasses import dataclass
from typing import Literal

from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingProfileCreationDTO:
    """Carry the original profile and assignments independently of live grants."""

    profile: EmbeddingProfileDTO
    operation: CompletedSynchronousOperationDTO
    project_access_revision: int
    initial_actions: tuple[EmbeddingProfileAction, ...]
    can_grant: Literal[True]
