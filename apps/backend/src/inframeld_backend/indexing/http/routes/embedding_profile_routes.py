from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, ClassVar, override
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.routes.action_grant_route import ActionGrantRoute
from inframeld_backend.indexing.application.protocols.embedding_profile_creator import (
    EmbeddingProfileCreator,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_reader import (
    EmbeddingProfileReader,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import (
    EmbeddingProfileId,
)
from inframeld_backend.indexing.http.mappers.embedding_profile_mapper import (
    EmbeddingProfileMapper,
)
from inframeld_backend.indexing.http.requests.embedding_profile_creation_request import (
    EmbeddingProfileCreationRequest,
)
from inframeld_backend.indexing.http.responses.embedding_profile_creation_response import (
    EmbeddingProfileCreationResponse,
)
from inframeld_backend.indexing.http.responses.embedding_profile_response import (
    EmbeddingProfileResponse,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
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

_COLLECTION = "/v1/projects/{project_id}/embedding-profiles"
_DETAIL = _COLLECTION + "/{embedding_profile_id}"


class _EmbeddingProfileRoute(ActionGrantRoute):
    _json_methods: ClassVar[frozenset[str]] = frozenset({"POST"})

    @override
    def _allowed_read_query(self) -> frozenset[str]:
        return frozenset({"limit", "cursor"}) if self.path == _COLLECTION else frozenset()


def create_embedding_profile_router(
    authenticate: ProductAccessDependency,
    open_creation: Callable[[], AbstractAsyncContextManager[EmbeddingProfileCreator]],
    open_reader: Callable[[], AbstractAsyncContextManager[EmbeddingProfileReader]],
    token_bound: ModelTokenBoundDTO,
) -> APIRouter:
    """Map native profile requests to the Indexing operations."""
    router = APIRouter(route_class=_EmbeddingProfileRoute)
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
        tags=["indexing"],
        operation_id="createEmbeddingProfile",
        status_code=201,
        responses=errors
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def create(
        project_id: UUID,
        body: EmbeddingProfileCreationRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> EmbeddingProfileCreationResponse:
        try:
            command = EmbeddingProfileMapper.command(ProjectId(project_id), body, token_bound)
        except ValueError:
            raise InvalidInputError("The Embedding Profile definition is unsupported.") from None
        context = IdempotencyContextDTO(
            HttpMethod.POST, _COLLECTION.format(project_id=project_id), key
        )
        async with open_creation() as creator:
            result = await creator.create(access=access, command=command, context=context)
        return EmbeddingProfileMapper.creation(result)

    @router.get(
        _COLLECTION, tags=["indexing"], operation_id="listEmbeddingProfiles", responses=errors
    )
    async def list_profiles(
        project_id: UUID,
        pagination: Annotated[PaginationQuery, Query()],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> PageResponse[EmbeddingProfileResponse]:
        async with open_reader() as reader:
            page = await reader.list_profiles(
                access, ProjectId(project_id), pagination.limit, pagination.cursor
            )
        return PageResponse[EmbeddingProfileResponse](
            items=[EmbeddingProfileMapper.profile(profile) for profile in page.items],
            next_cursor=page.next_cursor,
        )

    @router.get(_DETAIL, tags=["indexing"], operation_id="getEmbeddingProfile", responses=errors)
    async def get(
        project_id: UUID,
        embedding_profile_id: UUID,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> EmbeddingProfileResponse:
        async with open_reader() as reader:
            profile = await reader.get(
                access, ProjectId(project_id), EmbeddingProfileId(embedding_profile_id)
            )
        return EmbeddingProfileMapper.profile(profile)

    return router
