from abc import abstractmethod
from typing import Literal, Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_facts_dto import (
    EmbeddingProfileCreationFactsDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class EmbeddingProfileCreationRepository(Protocol):
    """Keep reference admission and profile creation in the caller's Project transaction."""

    @abstractmethod
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> EmbeddingProfileCreationFactsDTO | None:
        """Observe the exact Create action under the exclusive Project lock."""
        ...

    @abstractmethod
    async def lock_live_selection(
        self, *, facts: EmbeddingProfileCreationFactsDTO, connection_id: ModelConnectionId
    ) -> ModelConnectionAccessDTO | None:
        """Read live same-scope provider configuration under the liveness gate through commit."""
        ...

    @abstractmethod
    async def original(
        self,
        *,
        access: AccessContextDTO,
        facts: EmbeddingProfileCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> EmbeddingProfileCreationDTO:
        """Read the original for this actor and scope independently of live grants."""
        ...

    @abstractmethod
    async def save(
        self,
        *,
        access: AccessContextDTO,
        facts: EmbeddingProfileCreationFactsDTO,
        operation_id: OperationId,
        profile: EmbeddingProfileDTO,
        initial_actions: tuple[EmbeddingProfileAction, ...],
        can_grant: Literal[True],
    ) -> None:
        """Save the profile, layout, creator assignments, revision, audit and original result."""
        ...
