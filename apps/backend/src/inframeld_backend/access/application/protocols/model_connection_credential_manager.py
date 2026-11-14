from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


class ModelConnectionCredentialManager(Protocol):
    """Manage one connection's credential with current permission and safe original replay."""

    @abstractmethod
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionCredentialDTO: ...

    @abstractmethod
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeModelConnectionCredentialCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionCredentialResultDTO: ...
