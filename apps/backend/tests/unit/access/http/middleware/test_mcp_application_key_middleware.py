import asyncio
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send
from tests.support.application_key_scenarios import current_key_facts
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.mappers.mcp_access_context_mapper import MCPAccessContextMapper
from inframeld_backend.access.http.middleware.mcp_application_key_middleware import (
    MCPApplicationKeyMiddleware,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

KEY = "ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43
AUTHORIZATION = {"Authorization": "Bearer " + KEY}


def authenticator() -> MockApplicationAuthenticator:
    return MockApplicationAuthenticator(
        AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.application_key())
    )


def application(auth: MockApplicationAuthenticator) -> RequestContextMiddleware:
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "DELETE"])
    async def witness(request: Request, path: str) -> dict[str, str | bool]:
        access = MCPAccessContextMapper.from_scope(request.scope)
        return {
            "principalId": str(access.actor_principal_id.value),
            "authorizationPresent": "authorization" in request.headers,
        }

    return RequestContextMiddleware(MCPApplicationKeyMiddleware(app, authenticator=auth))


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/"), ("POST", "/tools/query"), ("DELETE", "/session/claimed")]
)
def test_entire_application_requires_a_header_on_every_method_and_path(
    method: str, path: str
) -> None:
    auth = authenticator()
    with TestClient(application(auth)) as client:
        response = client.request(method, path, headers={"Mcp-Session-Id": "old-session"})
    assert response.status_code == 401 and auth.calls == 0
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["www-authenticate"] == 'Bearer realm="inframeld"'


def test_each_request_gets_new_safe_evidence_and_the_secret_header_is_not_forwarded() -> None:
    auth = authenticator()
    with TestClient(application(auth)) as client:
        first = client.post("/tools/query", headers=AUTHORIZATION)
        auth.access = AccessContextDTO(
            PrincipalId(UUID(int=2)), MockAuthenticationEvidence.application_key()
        )
        second = client.get("/receipt", headers=AUTHORIZATION)
    assert first.json() == {"principalId": str(UUID(int=1)), "authorizationPresent": False}
    assert second.json() == {"principalId": str(UUID(int=2)), "authorizationPresent": False}
    assert auth.calls == 2
    assert KEY not in first.text + second.text


@pytest.mark.parametrize(
    "headers",
    [{"Authorization": "Bearer human-opaque"}, {"Cookie": "ory_kratos_session=human-cookie"}],
)
def test_human_families_are_unsupported_without_a_human_verifier(headers: dict[str, str]) -> None:
    auth = authenticator()
    with TestClient(application(auth)) as client:
        response = client.post("/tools/query", headers=headers)
    assert response.status_code == 401 and auth.calls == 0


def test_competing_cookie_and_header_are_400_before_authentication() -> None:
    auth = authenticator()
    with TestClient(application(auth)) as client:
        response = client.post(
            "/tools/query", headers=AUTHORIZATION | {"Cookie": "ory_kratos_session=human-cookie"}
        )
    assert response.status_code == 400 and auth.calls == 0
    assert response.json()["code"] == "invalid_authentication_request"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (AuthenticationRequiredError(), 401, "http_error"),
        (AccessDeniedError(), 403, "access_denied"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_rejection_ineligibility_and_uncertainty_keep_distinct_safe_problems(
    error: Exception, status: int, code: str
) -> None:
    auth = authenticator()
    auth.failure = error
    with TestClient(application(auth)) as client:
        response = client.post("/tools/query", headers=AUTHORIZATION)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text
    if status == 401:
        assert (
            response.headers["www-authenticate"]
            == 'Bearer realm="inframeld", error="invalid_token"'
        )


def test_unexpected_authentication_errors_are_not_relabelled_as_invalid_keys() -> None:
    auth = authenticator()
    auth.failure = RuntimeError("controlled implementation error")
    with (
        TestClient(application(auth)) as client,
        pytest.raises(RuntimeError, match="controlled implementation error"),
    ):
        client.post("/tools/query", headers=AUTHORIZATION)


class MockCurrentActionFacts(ProjectActionFactsReader):
    """Control fresh authority for the real authorizer, without qualifying SQL or verification."""

    def __init__(self, access: AccessContextDTO) -> None:
        evidence = access.authentication_evidence
        assert isinstance(evidence, ApplicationKeyAuthenticationDTO)
        principal = Principal(
            access.actor_principal_id,
            OrganizationId(UUID(int=2)),
            PrincipalKind.APPLICATION,
            PrincipalStatus.ACTIVE,
        )
        profile = ApplicationKeyVerificationProfileDTO(
            ApplicationKeyAudience("https://mcp.test/mcp/"), ApplicationKeyAdapter.MCP
        )
        key = current_key_facts(
            key_id=evidence.key_id,
            principal_id=principal.id,
            organization_id=principal.organization_id,
            project_id=ProjectId(UUID(int=3)),
        )
        self.facts = ProjectActionFactsDTO(
            principal=principal,
            has_pending_recovery=False,
            oauth_credential_facts=None,
            project_status=ProjectStatus.ACTIVE,
            is_project_member=True,
            has_exact_action_grant=True,
            application_key_facts=replace(
                key,
                audience=profile.audience,
                allowed_adapters=(ApplicationKeyAdapter.MCP,),
                expected_profile=profile,
            ),
        )
        self.failure: BaseException | None = None
        self.calls = 0

    @override
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.facts


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        ("revoked", 401, "http_error"),
        ("grant-removed", 403, "access_denied"),
        ("unconfirmed", 503, "dependency_unavailable"),
    ],
)
def test_real_authorizer_current_outcomes_are_mapped_before_dispatch(
    change: str, status: int, code: str
) -> None:
    auth = authenticator()
    facts = MockCurrentActionFacts(auth.access)
    authorizer = ActionAuthorizationService(facts)
    dispatched = 0

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal dispatched
        access = MCPAccessContextMapper.from_scope(scope)
        await authorizer.require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(ProjectId(UUID(int=3)), ActionId("build")),
        )
        dispatched += 1
        await JSONResponse({"admitted": True})(scope, receive, send)

    client = TestClient(
        RequestContextMiddleware(MCPApplicationKeyMiddleware(operation, authenticator=auth))
    )
    assert client.post("/tools/query", headers=AUTHORIZATION).status_code == 200
    if change == "revoked":
        key = facts.facts.application_key_facts
        assert key is not None
        facts.facts = replace(
            facts.facts, application_key_facts=replace(key, revoked_at=key.checked_at)
        )
    elif change == "grant-removed":
        facts.facts = replace(facts.facts, has_exact_action_grant=False)
    else:
        facts.failure = DependencyUnavailableError()
    response = client.post(
        "/tools/query", headers=AUTHORIZATION | {"Mcp-Session-Id": "old-session"}
    )
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text
    assert auth.calls == facts.calls == 2 and dispatched == 1
    if status == 401:
        assert (
            response.headers["www-authenticate"]
            == 'Bearer realm="inframeld", error="invalid_token"'
        )


def _scope() -> Scope:
    return {
        "type": "http",
        "method": "POST",
        "path": "/tools/query",
        "headers": [(b"authorization", ("Bearer " + KEY).encode())],
        "query_string": b"",
    }


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ApplicationKeyCredentialRejectedError(),
        AccessDeniedError(),
        DependencyUnavailableError(),
        RuntimeError("controlled downstream error"),
        asyncio.CancelledError(),
    ],
)
async def test_errors_after_response_start_propagate_without_a_second_response(
    error: BaseException,
) -> None:
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise error

    with pytest.raises(type(error)) as caught:
        await MCPApplicationKeyMiddleware(operation, authenticator=authenticator())(
            _scope(), _receive, send
        )
    assert caught.value is error
    assert [message["type"] for message in messages] == ["http.response.start"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [ApplicationKeyCredentialRejectedError(), AccessDeniedError(), DependencyUnavailableError()],
)
async def test_failed_start_send_keeps_unknown_response_ownership_and_never_retries(
    error: Exception,
) -> None:
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)
        raise error

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})

    with pytest.raises(type(error)) as caught:
        await MCPApplicationKeyMiddleware(operation, authenticator=authenticator())(
            _scope(), _receive, send
        )
    assert caught.value is error
    assert [message["type"] for message in messages] == ["http.response.start"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("controlled downstream error"), asyncio.CancelledError()]
)
async def test_unexpected_errors_and_cancellation_before_start_propagate_unchanged(
    error: BaseException,
) -> None:
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        raise error

    with pytest.raises(type(error)) as caught:
        await MCPApplicationKeyMiddleware(operation, authenticator=authenticator())(
            _scope(), _receive, send
        )
    assert caught.value is error
    assert not messages
