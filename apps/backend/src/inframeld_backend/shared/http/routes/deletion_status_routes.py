from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.shared.application.protocols.deletion_status_lookup import (
    DeletionStatusLookup,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INTERNAL_ERROR_PROBLEM,
    INVALID_INPUT_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.deletion_status_query_dependency import (
    DeletionStatusQueryDependency,
)
from inframeld_backend.shared.http.mappers.deletion_status_mapper import DeletionStatusMapper
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses
from inframeld_backend.shared.http.types.deletion_status_response import DeletionStatusResponse

_RESPONSES = (
    human_authentication_responses()
    | problem_responses(ACCESS_DENIED_PROBLEM)
    | problem_responses(VALIDATION_ERROR_PROBLEM)
    | problem_responses(INVALID_INPUT_PROBLEM)
    | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
    | problem_responses(INTERNAL_ERROR_PROBLEM)
)


def create_deletion_status_router(
    authenticate: ProductAccessDependency,
    open_lookup: Callable[[], AbstractAsyncContextManager[DeletionStatusLookup]],
) -> APIRouter:
    """Expose retained reads using supplied authentication and request-local lookup lifetime."""
    router = APIRouter(prefix="/v1")
    query_dependency = DeletionStatusQueryDependency()

    @router.get(
        "/deletions/status",
        operation_id="getDeletionStatus",
        tags=["operations"],
        responses=_RESPONSES,
    )
    async def lookup(
        response: Response,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        query: Annotated[GetDeletionStatusQuery, Depends(query_dependency)],
    ) -> DeletionStatusResponse:
        async with open_lookup() as service:
            result = await service.lookup(access=access, query=query)

        response.headers["Cache-Control"] = "no-store"
        return DeletionStatusMapper.to_response(result)

    return router
