from dataclasses import dataclass, field
from typing import override

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from inframeld_backend.access.application.commands.decide_human_oauth_consent_command import (
    DecideHumanOAuthConsentCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_consent_details_dto import (
    HumanOAuthConsentDetailsDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_oauth_consent_handler import (
    HumanOAuthConsentHandler,
)
from inframeld_backend.access.application.queries.inspect_human_oauth_consent_query import (
    InspectHumanOAuthConsentQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.routes.human_oauth_consent_routes import (
    create_human_oauth_consent_router,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

COOKIE = {"Cookie": "ory_kratos_session=private-cookie"}
WRITE = COOKIE | {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"}
BODY = {"consentChallenge": "private-challenge", "decision": "allow", "remember": True}


@dataclass
class MockConsentHandler(HumanOAuthConsentHandler):
    queries: list[InspectHumanOAuthConsentQuery] = field(
        default_factory=list[InspectHumanOAuthConsentQuery]
    )
    commands: list[DecideHumanOAuthConsentCommand] = field(
        default_factory=list[DecideHumanOAuthConsentCommand]
    )
    error: Exception | None = None

    @override
    async def inspect(
        self, *, credential: BrowserSessionCredential, query: InspectHumanOAuthConsentQuery
    ) -> HumanOAuthConsentDetailsDTO:
        assert credential.value == "private-cookie"
        self.queries.append(query)
        if self.error:
            raise self.error
        return HumanOAuthConsentDetailsDTO(
            VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice")),
            OAuthClientId("inframeld-cli"),
            HumanAPIAudience("https://api.test"),
            (HumanOAuthScope.API,),
            (HumanAPIAudience("https://api.test"),),
            True,
            3600,
        )

    @override
    async def decide(
        self, *, credential: BrowserSessionCredential, command: DecideHumanOAuthConsentCommand
    ) -> OAuthConsentContinuationDTO:
        assert credential.value == "private-cookie"
        self.commands.append(command)
        if self.error:
            raise self.error
        return OAuthConsentContinuationDTO(
            "https://auth.test/oauth2/auth?consent_verifier=private-verifier"
        )


def _app(handler: HumanOAuthConsentHandler | None) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    configure_problem_openapi(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(
        create_human_oauth_consent_router(
            handler, CSRFProtectionDependency((HttpUrl("https://account.test"),))
        )
    )
    return app


def test_inspection_returns_checked_display_fields_without_a_decision() -> None:
    handler = MockConsentHandler()
    with TestClient(_app(handler)) as client:
        response = client.get(
            "/v1/oauth/consent", params={"consent_challenge": "private-challenge"}, headers=COOKIE
        )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "accountSubject": "alice",
        "installation": "https://api.test",
        "clientId": "inframeld-cli",
        "requestedScopes": ["inframeld:api"],
        "requestedAudience": ["https://api.test"],
        "approvalRequired": True,
        "rememberConsentSeconds": 3600,
    }
    assert handler.queries[0].challenge.value == "private-challenge"
    assert not handler.commands
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_decision_maps_the_command_and_returns_only_the_continuation() -> None:
    handler = MockConsentHandler()
    with TestClient(_app(handler)) as client:
        response = client.post("/v1/oauth/consent", json=BODY, headers=WRITE)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "redirectTo": "https://auth.test/oauth2/auth?consent_verifier=private-verifier"
    }
    assert len(handler.commands) == 1
    command = handler.commands[0]
    assert command.challenge.value == "private-challenge"
    assert command.decision.value == "allow"
    assert command.remember is True
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 401),
        ({"Authorization": "Bearer human"}, 400),
        ({"Authorization": "Bearer ifm_app_key"}, 400),
        (COOKIE | {"Authorization": "Bearer human"}, 400),
        ({"Cookie": "ory_kratos_session=a; ory_kratos_session=b"}, 400),
    ],
)
def test_cookie_is_the_only_unambiguous_credential(headers: dict[str, str], status: int) -> None:
    handler = MockConsentHandler()
    with TestClient(_app(handler)) as client:
        response = client.get(
            "/v1/oauth/consent?consent_challenge=private-challenge", headers=headers
        )
    assert response.status_code == status, response.text
    assert not handler.queries
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "headers",
    [
        COOKIE,
        COOKIE | {"Origin": "https://account.test"},
        COOKIE | {"X-Inframeld-CSRF": "1"},
        COOKIE | {"Origin": "https://evil.test", "X-Inframeld-CSRF": "1"},
    ],
)
def test_csrf_failure_never_submits_a_provider_decision(headers: dict[str, str]) -> None:
    handler = MockConsentHandler()
    with TestClient(_app(handler)) as client:
        response = client.post("/v1/oauth/consent", json=BODY, headers=headers)
    assert response.status_code == 403, response.text
    assert not handler.commands


@pytest.mark.parametrize(
    "patch",
    [
        {"decision": "other"},
        {"remember": "yes"},
        {"rememberFor": 0},
        {"subject": "bob"},
        {"requestedAudience": ["https://evil.test"]},
        {"consentChallenge": " "},
    ],
)
def test_browser_cannot_choose_provider_scope_or_duration(patch: dict[str, object]) -> None:
    handler = MockConsentHandler()
    with TestClient(_app(handler)) as client:
        response = client.post("/v1/oauth/consent", json=BODY | patch, headers=WRITE)
    assert response.status_code == 422, response.text
    assert not handler.commands
    assert "private-challenge" not in response.text


@pytest.mark.parametrize(
    "error,status",
    [
        (AccessDeniedError(), 403),
        (AuthenticationRequiredError(), 401),
        (ResourceNotFoundError(), 404),
        (DependencyUnavailableError(), 503),
    ],
)
def test_failures_use_the_existing_safe_problem_contract(error: Exception, status: int) -> None:
    handler = MockConsentHandler(error=error)
    with TestClient(_app(handler)) as client:
        response = client.post("/v1/oauth/consent", json=BODY, headers=WRITE)
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert "private-challenge" not in response.text
    assert response.headers["Cache-Control"] == "no-store"


def test_unconfigured_consent_is_unavailable_without_removing_the_public_contract() -> None:
    with TestClient(_app(None)) as client:
        response = client.get(
            "/v1/oauth/consent?consent_challenge=private-challenge", headers=COOKIE
        )
    assert response.status_code == 503
