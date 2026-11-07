from collections.abc import Mapping
from http import HTTPStatus

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.protocols.application_authenticator import (
    ApplicationAuthenticator,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.http.mappers.incoming_credential_mapper import (
    IncomingCredentialMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.builders.problem_response import build_problem_response
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    INVALID_AUTHENTICATION_REQUEST_PROBLEM,
)
from inframeld_backend.shared.http.mappers.problem_mapper import (
    for_application_error,
    for_http_status,
)
from inframeld_backend.shared.http.validation.invalid_authentication_request_error import (
    InvalidAuthenticationRequestError,
)


class MCPApplicationKeyMiddleware:
    """Authenticate every HTTP request before the entire downstream ASGI application.

    Bootstrap supplies an authenticator bound to its explicit MCP verification
    profile. Downstream authorizers receive that same trusted constructor profile
    separately. Neither request state nor protocol session IDs select an audience.
    Safe authorization problems are emitted only before a response start is attempted.
    """

    def __init__(self, app: ASGIApp, *, authenticator: ApplicationAuthenticator) -> None:
        self.app = app
        self._authenticator = authenticator

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        response_start_attempted = False

        async def send_response(message: Message) -> None:
            nonlocal response_start_attempted
            if message["type"] == "http.response.start":
                # A failed send leaves ownership unknown, so never replace that response.
                response_start_attempted = True
            await send(message)

        try:
            credential = IncomingCredentialMapper.select(
                authorization_headers=request.headers.getlist("Authorization"),
                cookies=request.cookies,
            )
            if not isinstance(credential, ApplicationKeyCredential):
                raise IncomingCredentialMapper.unauthorized(
                    invalid_token=bool(request.headers.getlist("Authorization"))
                )
            access = await self._authenticator.authenticate(credential)
            if not isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
                raise RuntimeError("The MCP authenticator returned another credential family.")
            # Copy request state so a shared lifespan state never retains an actor.
            state: Mapping[str, object] = scope.get("state", {})
            authenticated_scope: Scope = dict(scope)
            authenticated_scope["state"] = dict(state) | {"inframeld_mcp_access": access}
            authenticated_scope["headers"] = [
                (name, value)
                for name, value in scope["headers"]
                if name.lower() != b"authorization"
            ]
            await self.app(authenticated_scope, receive, send_response)
            return
        except AuthenticationRequiredError:
            if response_start_attempted:
                raise
            response = build_problem_response(
                request,
                for_http_status(HTTPStatus.UNAUTHORIZED),
                protocol_headers=IncomingCredentialMapper.unauthorized(invalid_token=True).headers,
            )
        except (AccessDeniedError, DependencyUnavailableError) as error:
            if response_start_attempted:
                raise
            response = build_problem_response(request, for_application_error(error))
        except InvalidAuthenticationRequestError as error:
            if response_start_attempted:
                raise
            response = build_problem_response(
                request, INVALID_AUTHENTICATION_REQUEST_PROBLEM, protocol_headers=error.headers
            )
        except HTTPException as error:
            if response_start_attempted:
                raise
            response = build_problem_response(
                request, for_http_status(error.status_code), protocol_headers=error.headers
            )
        await response(scope, receive, send)
