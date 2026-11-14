"""Supply controlled model-connection wire outcomes without starting a model provider."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.dtos.model_connection_grant_item_dto import (
    ModelConnectionGrantItemDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_result_dto import (
    ModelConnectionGrantResultDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grants_page_dto import (
    ModelConnectionGrantsPageDTO,
)
from inframeld_backend.access.application.dtos.model_connections_page_dto import (
    ModelConnectionsPageDTO,
)
from inframeld_backend.access.application.protocols.model_connection_creator import (
    ModelConnectionCreator,
)
from inframeld_backend.access.application.protocols.model_connection_grant_changer import (
    ModelConnectionGrantChanger,
)
from inframeld_backend.access.application.protocols.model_connection_grants_reader import (
    ModelConnectionGrantsReader,
)
from inframeld_backend.access.application.protocols.model_connection_reader import (
    ModelConnectionReader,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
SDK_MODEL_CONNECTION_ID = ModelConnectionId(UUID("00000000-0000-4000-8000-000000000030"))
_ACTOR = PrincipalId(UUID("00000000-0000-4000-8000-000000000001"))
_RECIPIENT = PrincipalId(UUID("00000000-0000-4000-8000-000000000004"))
_UNCHANGED = PrincipalId(UUID("00000000-0000-4000-8000-000000000005"))
_NOW = datetime(2030, 1, 1, tzinfo=UTC)
_CONNECTION = ModelConnectionDTO(
    _PROJECT,
    SDK_MODEL_CONNECTION_ID,
    ResourceName("company-gateway"),
    "Company gateway",
    ModelConnectionAccessDTO(
        ModelConnectionProvider.OPENAI_COMPATIBLE,
        "https://models.example.test/v1",
        None,
        ModelConnectionAuthentication.API_KEY,
    ),
    0,
    False,
    0,
)


class MockSDKModelConnections(
    ModelConnectionCreator,
    ModelConnectionReader,
    ModelConnectionGrantChanger,
    ModelConnectionGrantsReader,
):
    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateModelConnectionCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionCreationDTO:
        if access.actor_principal_id != _ACTOR:
            raise AccessDeniedError()
        if command.project_id != _PROJECT:
            raise ResourceNotFoundError()
        return ModelConnectionCreationDTO(
            replace(
                _CONNECTION,
                name=command.name,
                display_name=command.display_name.value,
                access=command.access,
            ),
            CompletedSynchronousOperationDTO(
                OperationId("sdk-model-connection-create"),
                True,
                OperationReplayKind.SAFE_RESULT,
                _NOW,
            ),
            8,
            tuple(ModelConnectionAction),
        )

    @override
    async def get(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
    ) -> ModelConnectionDTO:
        if project_id != _PROJECT or connection_id != SDK_MODEL_CONNECTION_ID:
            raise ResourceNotFoundError()
        return _CONNECTION

    @override
    async def list_connections(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        limit: int,
        cursor: str | None,
    ) -> ModelConnectionsPageDTO:
        if project_id != _PROJECT:
            raise ResourceNotFoundError()
        return ModelConnectionsPageDTO((_CONNECTION,), None)

    @override
    async def list_usage(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        limit: int,
        cursor: str | None,
    ) -> None:
        await self.get(access, project_id, connection_id)

    @override
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeModelConnectionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionGrantResultDTO:
        if access.actor_principal_id != _ACTOR:
            raise AccessDeniedError()
        if command.model_connection_id != SDK_MODEL_CONNECTION_ID:
            raise ResourceNotFoundError()
        changed = command.recipient_id != _UNCHANGED
        return ModelConnectionGrantResultDTO(
            ModelConnectionGrantTargetDTO(_PROJECT, SDK_MODEL_CONNECTION_ID),
            command.recipient_id,
            command.action,
            command.can_grant,
            command.expected_access_revision + int(changed),
            changed,
            201 if command.can_grant is not None and changed else 200,
            CompletedSynchronousOperationDTO(
                OperationId(f"sdk-model-connection-grant-{context.method.value.lower()}"),
                True,
                OperationReplayKind.SAFE_RESULT,
                _NOW,
            ),
        )

    @override
    async def list_grants(
        self,
        access: AccessContextDTO,
        connection_id: ModelConnectionId,
        action: ModelConnectionAction,
        limit: int,
        cursor: str | None,
    ) -> ModelConnectionGrantsPageDTO:
        if access.actor_principal_id != _ACTOR:
            raise AccessDeniedError()
        if connection_id != SDK_MODEL_CONNECTION_ID:
            raise ResourceNotFoundError()
        return ModelConnectionGrantsPageDTO((ModelConnectionGrantItemDTO(_RECIPIENT, True),), None)


@asynccontextmanager
async def open_model_connections() -> AsyncGenerator[MockSDKModelConnections]:
    yield MockSDKModelConnections()
