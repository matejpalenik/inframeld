from abc import abstractmethod
from typing import Literal, Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profile_creation_facts_dto import (
    ProcessingProfileCreationFactsDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProcessingProfileCreationRepository(Protocol):
    """Keep profile creation and replay bound to the caller's Project transaction."""

    @abstractmethod
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProcessingProfileCreationFactsDTO | None:
        """Require an active transaction and observe the exact create action under the Project lock."""
        ...

    @abstractmethod
    async def original(
        self,
        *,
        access: AccessContextDTO,
        facts: ProcessingProfileCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProcessingProfileCreationDTO:
        """Read the saved original for this actor and scope independently of live grants."""
        ...

    @abstractmethod
    async def save(
        self,
        *,
        access: AccessContextDTO,
        facts: ProcessingProfileCreationFactsDTO,
        operation_id: OperationId,
        profile: ProcessingProfileDTO,
        initial_actions: tuple[ProcessingProfileAction, ...],
        can_grant: Literal[True],
    ) -> None:
        """Save the profile, exact creator grants, next Access revision, audit and original result."""
        ...
