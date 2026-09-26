"""Expose the authenticated local human to the browser client."""

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.requests import Request

from inframeld_backend.access.application.access_authorizer import AccessContext
from inframeld_backend.access.domain.values import PrincipalId
from inframeld_backend.shared.http.problem_definitions import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
)
from inframeld_backend.shared.http.problem_mapper import for_http_status
from inframeld_backend.shared.http.problem_openapi import problem_responses


class CurrentSessionResponse(BaseModel):
    principal_id: PrincipalId = Field(serialization_alias="principalId")


def create_session_router(authenticate: Callable[[Request], Awaitable[AccessContext]]) -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.get(
        "/session",
        tags=["access"],
        operation_id="getCurrentSession",
        responses=(
            problem_responses(for_http_status(HTTPStatus.UNAUTHORIZED))
            | problem_responses(ACCESS_DENIED_PROBLEM)
            | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        ),
    )
    async def current_session(
        access: Annotated[AccessContext, Depends(authenticate)],
    ) -> CurrentSessionResponse:
        return CurrentSessionResponse(principal_id=access.actor_principal_id)

    return router
