from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_processing_profile_grant_command import (
    ChangeProcessingProfileGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.processing_profile_grant_facts_dto import (
    ProcessingProfileGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_item_dto import (
    ProcessingProfileGrantItemDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_result_dto import (
    ProcessingProfileGrantResultDTO,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProcessingProfileGrantRepository(Protocol):
    @abstractmethod
    async def lock_for_change(
        self, access: AccessContextDTO, command: ChangeProcessingProfileGrantCommand
    ) -> ProcessingProfileGrantFactsDTO | None: ...

    @abstractmethod
    async def original(
        self, facts: ProcessingProfileGrantFactsDTO, operation: CompletedSynchronousOperationDTO
    ) -> ProcessingProfileGrantResultDTO: ...

    @abstractmethod
    async def save_change(
        self,
        facts: ProcessingProfileGrantFactsDTO,
        recipient_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None: ...

    @abstractmethod
    async def save_result(
        self, facts: ProcessingProfileGrantFactsDTO, result: ProcessingProfileGrantResultDTO
    ) -> None: ...

    @abstractmethod
    async def lock_for_read(
        self,
        access: AccessContextDTO,
        profile_id: ProcessingProfileId,
        action: ProcessingProfileAction,
    ) -> ProcessingProfileGrantFactsDTO | None: ...

    @abstractmethod
    async def list_assignments(
        self,
        facts: ProcessingProfileGrantFactsDTO,
        after: PrincipalId | None,
        limit: int,
    ) -> tuple[ProcessingProfileGrantItemDTO, ...]: ...
