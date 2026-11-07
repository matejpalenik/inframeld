from typing import Annotated

from fastapi import APIRouter, Depends, Response

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.application_session_reader import (
    ApplicationSessionReader,
)
from inframeld_backend.access.http.dependencies.application_key_dependency import (
    ApplicationKeyDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.responses.current_application_session_response import (
    CurrentApplicationSessionResponse,
)
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses


def create_application_session_router(
    authenticate: ApplicationKeyDependency, reader: ApplicationSessionReader
) -> APIRouter:
    """Expose current application identity after fresh credential and admission checks."""
    router = APIRouter(prefix="/v1")

    @router.get(
        "/application-session",
        operation_id="getCurrentApplicationSession",
        tags=["access"],
        responses=(
            human_authentication_responses()
            | problem_responses(ACCESS_DENIED_PROBLEM)
            | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        ),
    )
    async def current_application_session(
        response: Response, access: Annotated[AccessContextDTO, Depends(authenticate)]
    ) -> CurrentApplicationSessionResponse:
        current = await reader.read(access=access)
        response.headers["Cache-Control"] = "no-store"
        return CurrentApplicationSessionResponse(
            principal_id=current.principal_id.value,
            project_id=current.project_id.value,
        )

    return router
