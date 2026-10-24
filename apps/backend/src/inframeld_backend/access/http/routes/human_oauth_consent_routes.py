from http import HTTPStatus
from typing import Annotated, override

from fastapi import APIRouter, Depends, Query
from fastapi.routing import APIRoute
from pydantic import SecretStr
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.access.application.protocols.human_oauth_consent_handler import (
    HumanOAuthConsentHandler,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_oauth_consent_dependency import (
    HumanOAuthConsentDependency,
)
from inframeld_backend.access.http.mappers.human_oauth_consent_mapper import HumanOAuthConsentMapper
from inframeld_backend.access.http.requests.human_oauth_consent_request import (
    HumanOAuthConsentRequest,
)
from inframeld_backend.access.http.responses.human_oauth_consent_decision_response import (
    HumanOAuthConsentDecisionResponse,
)
from inframeld_backend.access.http.responses.human_oauth_consent_details_response import (
    HumanOAuthConsentDetailsResponse,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_AUTHENTICATION_REQUEST_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses

_RESPONSES = (
    problem_responses(ACCESS_DENIED_PROBLEM)
    | problem_responses(INVALID_AUTHENTICATION_REQUEST_PROBLEM)
    | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
    | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
    | problem_responses(VALIDATION_ERROR_PROBLEM)
    | problem_responses(for_http_status(HTTPStatus.UNAUTHORIZED))
)


class _ConsentRoute(APIRoute):
    """Keep consent results and handled problem responses out of browser caches."""

    @override
    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def private_response(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in {b"cache-control", b"referrer-policy"}
                ]
                headers.extend(
                    [(b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer")]
                )
                message = {**message, "headers": headers}
            await send(message)

        await super().handle(scope, receive, private_response)


def create_human_oauth_consent_router(
    handler: HumanOAuthConsentHandler | None, csrf: CSRFProtectionDependency
) -> APIRouter:
    """Expose consent separately from product admission and bearer authentication."""
    router = APIRouter(prefix="/v1/oauth", route_class=_ConsentRoute)
    credential_dependency = HumanOAuthConsentDependency(csrf)

    @router.get(
        "/consent", tags=["access"], operation_id="inspectHumanOAuthConsent", responses=_RESPONSES
    )
    async def inspect_consent(
        consent_challenge: Annotated[SecretStr, Query(min_length=1)],
        credential: Annotated[BrowserSessionCredential, Depends(credential_dependency)],
    ) -> HumanOAuthConsentDetailsResponse:
        query = HumanOAuthConsentMapper.to_query(consent_challenge)
        if handler is None:
            raise DependencyUnavailableError()
        result = await handler.inspect(credential=credential, query=query)
        return HumanOAuthConsentMapper.to_details_response(result)

    @router.post(
        "/consent", tags=["access"], operation_id="decideHumanOAuthConsent", responses=_RESPONSES
    )
    async def decide_consent(
        body: HumanOAuthConsentRequest,
        credential: Annotated[BrowserSessionCredential, Depends(credential_dependency)],
    ) -> HumanOAuthConsentDecisionResponse:
        command = HumanOAuthConsentMapper.to_command(body)
        if handler is None:
            raise DependencyUnavailableError()
        result = await handler.decide(credential=credential, command=command)
        return HumanOAuthConsentMapper.to_decision_response(result)

    return router
