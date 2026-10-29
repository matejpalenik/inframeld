from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.mappers.original_operation_lookup_mapper import (
    OriginalOperationLookupMapper,
)
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses
from inframeld_backend.shared.http.requests.original_operation_lookup_request import (
    OriginalOperationLookupRequest,
)
from inframeld_backend.shared.http.routes.operation_lookup_route import OperationLookupRoute
from inframeld_backend.shared.http.types.operation_lookup_response import OperationLookupResponse

_RESPONSES = (
    human_authentication_responses()
    | problem_responses(ACCESS_DENIED_PROBLEM)
    | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
    | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
    | problem_responses(VALIDATION_ERROR_PROBLEM)
    | problem_responses(INVALID_INPUT_PROBLEM)
    | problem_responses(for_http_status(413))
    | problem_responses(for_http_status(415))
)


def create_original_operation_lookup_router(
    authenticate: HumanSessionDependency,
    open_lookup: Callable[[], AbstractAsyncContextManager[OriginalOperationLookup]],
) -> APIRouter:
    """Expose read-only original admission lookup through current human authentication."""
    router = APIRouter(prefix="/v1", route_class=OperationLookupRoute)

    @router.post(
        "/operations/lookup",
        operation_id="lookupOriginalOperation",
        tags=["operations"],
        responses=_RESPONSES,
    )
    async def lookup(
        body: OriginalOperationLookupRequest,
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> OperationLookupResponse:
        query = OriginalOperationLookupMapper.to_query(body)
        async with open_lookup() as service:
            result = await service.lookup(access=access, query=query)
        return OriginalOperationLookupMapper.to_response(result)

    return router
