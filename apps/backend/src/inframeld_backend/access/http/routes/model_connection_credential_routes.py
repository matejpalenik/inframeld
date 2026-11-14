from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, ClassVar, override
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.model_connection_credential_manager import (
    ModelConnectionCredentialManager,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.model_connection_credential_mapper import (
    ModelConnectionCredentialMapper,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.model_connection_credential_request import (
    ModelConnectionCredentialRequest,
)
from inframeld_backend.access.http.responses.model_connection_credential_details_response import (
    ModelConnectionCredentialDetailsResponse,
)
from inframeld_backend.access.http.responses.model_connection_credential_result_response import (
    ModelConnectionCredentialResultResponse,
)
from inframeld_backend.access.http.routes.action_grant_route import ActionGrantRoute
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.idempotency_key_dependency import (
    IdempotencyKeyDependency,
)
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses

_ROUTE = "/v1/projects/{project_id}/model-connections/{model_connection_id}/credential"
_EXPECTED_REVISION = "expectedCredentialRevision"


class _CredentialRoute(ActionGrantRoute):
    # A full decoded token can occupy six times its size when escaped in JSON.
    _json_body_limit: ClassVar[int] = 100 * 1024
    _delete_revision_query: ClassVar[str] = _EXPECTED_REVISION

    @override
    def _allowed_read_query(self) -> frozenset[str]:
        return frozenset()


def create_model_connection_credential_router(
    authenticate: ProductAccessDependency,
    open_credentials: Callable[[], AbstractAsyncContextManager[ModelConnectionCredentialManager]],
) -> APIRouter:
    router = APIRouter(route_class=_CredentialRoute)
    idempotency_key = IdempotencyKeyDependency()
    errors = (
        human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
    )
    mutation_errors = errors | problem_responses(CONFLICT_PROBLEM)

    @router.get(
        _ROUTE, tags=["access"], operation_id="getModelConnectionCredential", responses=errors
    )
    async def get(
        project_id: UUID,
        model_connection_id: UUID,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ModelConnectionCredentialDetailsResponse:
        async with open_credentials() as manager:
            credential = await manager.get(
                access, ProjectId(project_id), ModelConnectionId(model_connection_id)
            )
        return ModelConnectionCredentialMapper.details(credential)

    async def change(
        access: AccessContextDTO,
        key: IdempotencyKey,
        command: ChangeModelConnectionCredentialCommand,
    ) -> ModelConnectionCredentialResultResponse:
        method = HttpMethod.DELETE if command.value is None else HttpMethod.PUT
        context = IdempotencyContextDTO(
            method,
            _ROUTE.format(
                project_id=command.project_id.value, model_connection_id=command.connection_id.value
            ),
            key,
        )
        async with open_credentials() as manager:
            result = await manager.change(access, command, context)
        return ModelConnectionCredentialMapper.result(result)

    @router.put(
        _ROUTE,
        tags=["access"],
        operation_id="putModelConnectionCredential",
        responses=mutation_errors
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def put(
        project_id: UUID,
        model_connection_id: UUID,
        body: ModelConnectionCredentialRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(idempotency_key)],
    ) -> ModelConnectionCredentialResultResponse:
        return await change(
            access,
            key,
            ChangeModelConnectionCredentialCommand(
                ProjectId(project_id),
                ModelConnectionId(model_connection_id),
                body.expected_credential_revision,
                ProviderCredentialValue(body.value.get_secret_value()),
            ),
        )

    @router.delete(
        _ROUTE,
        tags=["access"],
        operation_id="removeModelConnectionCredential",
        responses=mutation_errors,
    )
    async def remove(
        project_id: UUID,
        model_connection_id: UUID,
        expected_revision: Annotated[
            int,
            Query(
                alias=_EXPECTED_REVISION,
                ge=0,
                le=RevisionValidation.MAX_VALUE,
                json_schema_extra={"format": "int64"},
            ),
        ],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(idempotency_key)],
    ) -> ModelConnectionCredentialResultResponse:
        return await change(
            access,
            key,
            ChangeModelConnectionCredentialCommand(
                ProjectId(project_id),
                ModelConnectionId(model_connection_id),
                expected_revision,
                None,
            ),
        )

    return router
