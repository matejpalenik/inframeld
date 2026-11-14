from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, ClassVar, override
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.model_connection_creator import (
    ModelConnectionCreator,
)
from inframeld_backend.access.application.protocols.model_connection_reader import (
    ModelConnectionReader,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.mappers.model_connection_mapper import ModelConnectionMapper
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.model_connection_creation_request import (
    ModelConnectionCreationRequest,
)
from inframeld_backend.access.http.responses.model_connection_creation_response import (
    ModelConnectionCreationResponse,
)
from inframeld_backend.access.http.responses.model_connection_response import (
    ModelConnectionResponse,
)
from inframeld_backend.access.http.responses.model_connection_usage_response import (
    ModelConnectionUsageResponse,
)
from inframeld_backend.access.http.routes.action_grant_route import ActionGrantRoute
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
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
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse

_COLLECTION = "/v1/projects/{project_id}/model-connections"
_DETAIL = _COLLECTION + "/{model_connection_id}"
_USAGE = _DETAIL + "/usage"


class _ModelConnectionRoute(ActionGrantRoute):
    _json_methods: ClassVar[frozenset[str]] = frozenset({"POST"})

    @override
    def _allowed_read_query(self) -> frozenset[str]:
        return frozenset({"limit", "cursor"}) if self.path in {_COLLECTION, _USAGE} else frozenset()


def create_model_connection_router(
    authenticate: ProductAccessDependency,
    open_creator: Callable[[], AbstractAsyncContextManager[ModelConnectionCreator]],
    open_reader: Callable[[], AbstractAsyncContextManager[ModelConnectionReader]],
) -> APIRouter:
    router = APIRouter(route_class=_ModelConnectionRoute)
    errors = (
        human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
    )
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        _COLLECTION,
        tags=["access"],
        operation_id="createModelConnection",
        status_code=201,
        responses=errors
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def create(
        project_id: UUID,
        body: ModelConnectionCreationRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> ModelConnectionCreationResponse:
        context = IdempotencyContextDTO(
            HttpMethod.POST, _COLLECTION.format(project_id=project_id), key
        )
        async with open_creator() as creator:
            result = await creator.create(
                access=access,
                command=ModelConnectionMapper.command(ProjectId(project_id), body),
                context=context,
            )
        return ModelConnectionMapper.creation(result)

    @router.get(_COLLECTION, tags=["access"], operation_id="listModelConnections", responses=errors)
    async def list_connections(
        project_id: UUID,
        pagination: Annotated[PaginationQuery, Query()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[ModelConnectionResponse]:
        async with open_reader() as reader:
            page = await reader.list_connections(
                access, ProjectId(project_id), pagination.limit, pagination.cursor
            )
        return PageResponse[ModelConnectionResponse](
            items=[ModelConnectionMapper.connection(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @router.get(_DETAIL, tags=["access"], operation_id="getModelConnection", responses=errors)
    async def get(
        project_id: UUID,
        model_connection_id: UUID,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ModelConnectionResponse:
        async with open_reader() as reader:
            result = await reader.get(
                access, ProjectId(project_id), ModelConnectionId(model_connection_id)
            )
        return ModelConnectionMapper.connection(result)

    @router.get(_USAGE, tags=["access"], operation_id="listModelConnectionUsage", responses=errors)
    async def list_usage(
        project_id: UUID,
        model_connection_id: UUID,
        pagination: Annotated[PaginationQuery, Query()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[ModelConnectionUsageResponse]:
        async with open_reader() as reader:
            await reader.list_usage(
                access,
                ProjectId(project_id),
                ModelConnectionId(model_connection_id),
                pagination.limit,
                pagination.cursor,
            )
        return PageResponse[ModelConnectionUsageResponse](items=[], next_cursor=None)

    return router
