from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_facts_dto import (
    ModelConnectionCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ModelConnectionCredentialRepository(Protocol):
    """Keep exact permission, slot, audit, and receipt in the caller's transaction."""

    @abstractmethod
    async def inspect(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        *,
        for_write: bool,
    ) -> ModelConnectionCredentialFactsDTO | None: ...

    @abstractmethod
    async def original(
        self,
        facts: ModelConnectionCredentialFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ModelConnectionCredentialResultDTO: ...

    @abstractmethod
    async def save(
        self,
        facts: ModelConnectionCredentialFactsDTO,
        credential: ModelConnectionCredentialDTO,
        envelope: EncryptedProviderCredentialDTO | None,
        operation_id: OperationId,
    ) -> None: ...

    @abstractmethod
    async def save_result(
        self, facts: ModelConnectionCredentialFactsDTO, result: ModelConnectionCredentialResultDTO
    ) -> None: ...
