"""Expose the authenticated local human to browser and CLI clients."""

from typing import Annotated

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.current_session_response import CurrentSessionResponse
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses


def create_session_router(authenticate: HumanSessionDependency) -> APIRouter:
    """Register the current-session endpoint using the supplied authentication dependency."""
    router = APIRouter(prefix="/v1")

    @router.get(
        "/session",
        tags=["access"],
        # Preserve the published schema while keeping internal purpose documentation.
        openapi_extra={"description": None},
        operation_id="getCurrentSession",
        responses=(
            human_authentication_responses()
            | problem_responses(ACCESS_DENIED_PROBLEM)
            | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        ),
    )
    async def current_session(
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> CurrentSessionResponse:
        """Convert the admitted caller's principal ID to the existing public session response."""
        return CurrentSessionResponse(principal_id=access.actor_principal_id.value)

    return router
