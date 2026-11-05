from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.human_admission_scenarios import (
    ACCESS,
    ALICE,
    BOB,
    COMMAND,
    CONTEXT,
    IDENTITY,
    ORG,
    HumanAdmissionScenario,
)

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_admitter import HumanAdmitter
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.human_admission_routes import (
    create_human_admission_router,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.errors.application_error import ApplicationError
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

ROUTE = f"/v1/organizations/{ORG.value}/human-admissions"
BODY = {"identityId": IDENTITY.subject.value, "expectedAccessRevision": 7}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "admit-bob",
}


class MockAdmissionAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self,
        credential: BrowserSessionCredential | HumanAccessTokenCredential | None,
    ) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError()
        return ACCESS


class MockHumanAdmitter(HumanAdmitter):
    def __init__(self, changed: bool = True, replay: bool = False) -> None:
        original = HumanAdmissionScenario().results.result
        self.result = replace(
            original, changed=changed, operation=replace(original.operation, created=not replay)
        )
        self.calls: list[tuple[AdmitHumanCommand, IdempotencyContextDTO]] = []
        self.error: ApplicationError | None = None

    @override
    async def admit(
        self,
        *,
        access: AccessContextDTO,
        command: AdmitHumanCommand,
        context: IdempotencyContextDTO,
    ) -> HumanAdmissionResultDTO:
        assert access.actor_principal_id == ALICE.id
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return self.result


def client_for(service: MockHumanAdmitter, *, hydra: bool = True) -> TestClient:
    @asynccontextmanager
    async def open_admitter() -> AsyncGenerator[MockHumanAdmitter]:
        yield service

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    auth = MockAdmissionAuthenticator()
    app.include_router(
        create_human_admission_router(
            HumanSessionDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth if hydra else None,
            ),
            open_admitter,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "changed,replay", [(True, False), (True, True), (False, False), (False, True)]
)
def test_original_business_status_and_receipt_survive_replay(changed: bool, replay: bool) -> None:
    service = MockHumanAdmitter(changed, replay)
    with client_for(service) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == (201 if changed else 200)
    assert response.json() == {
        "operationId": "metadata-original",
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
        "organizationId": str(ORG.value),
        "principalId": str(BOB.id.value),
        "accessRevision": 8,
        "changed": changed,
    }
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == [(COMMAND, CONTEXT)]


def test_cookie_route_needs_no_hydra_authenticator() -> None:
    service = MockHumanAdmitter()
    with client_for(service, hydra=False) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 201 and len(service.calls) == 1


def test_human_bearer_needs_no_cookie_csrf() -> None:
    service = MockHumanAdmitter()
    with client_for(service) as client:
        response = client.post(
            ROUTE,
            json=BODY,
            headers={"Authorization": "Bearer controlled-token", "Idempotency-Key": "admit-bob"},
        )
    assert response.status_code == 201 and len(service.calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "expectedAccessRevision": True},
        {**BODY, "expectedAccessRevision": "7"},
        {**BODY, "expectedAccessRevision": 7.0},
        {**BODY, "expectedAccessRevision": -1},
        {**BODY, "expectedAccessRevision": 2**63},
        {**BODY, "identityId": "invalid"},
        {**BODY, "unknown": "private-marker"},
        {"identityId": BODY["identityId"]},
    ],
)
def test_invalid_body_has_no_admission_effect(body: dict[str, object]) -> None:
    service = MockHumanAdmitter()
    with client_for(service) as client:
        response = client.post(ROUTE, json=body, headers=HEADERS)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store" and not service.calls
    assert "private-marker" not in response.text


@pytest.mark.parametrize(
    "raw,status",
    [
        (
            '{"identityId":"'
            + IDENTITY.subject.value
            + '","expectedAccessRevision":7,"expectedAccessRevision":8}',
            422,
        ),
        ('{"identityId":"' + IDENTITY.subject.value + '","expectedAccessRevision":NaN}', 422),
        ("[1,2]", 422),
        ("{", 422),
        ('{"pad":"' + "a" * 32768 + '"}', 413),
    ],
    ids=["duplicate-json", "nonfinite", "array", "malformed", "oversized"],
)
def test_json_bytes_are_bounded_and_unambiguous(raw: str, status: int) -> None:
    service = MockHumanAdmitter()
    with client_for(service) as client:
        response = client.post(
            ROUTE, content=raw, headers={**HEADERS, "Content-Type": "application/json"}
        )
    assert response.status_code == status and not service.calls
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["cache-control"] == "no-store"
    if status == 422:
        assert response.json()["code"] == "invalid_input"


def test_wrong_media_type_rejected_before_admission() -> None:
    service = MockHumanAdmitter()
    with client_for(service) as client:
        response = client.post(
            ROUTE, content="private-marker", headers={**HEADERS, "Content-Type": "text/plain"}
        )
    assert response.status_code == 415 and not service.calls
    assert response.headers["cache-control"] == "no-store" and "private-marker" not in response.text


def test_duplicate_idempotency_headers_rejected_before_admission() -> None:
    service = MockHumanAdmitter()
    with client_for(service) as client:
        response = client.post(
            ROUTE, json=BODY, headers=[*HEADERS.items(), ("Idempotency-Key", "other")]
        )
    assert response.status_code == 422 and not service.calls
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("removed", ["Cookie", "Origin", "X-Inframeld-CSRF"])
def test_current_human_and_cookie_csrf_precede_admission(removed: str) -> None:
    service = MockHumanAdmitter()
    with client_for(service) as client:
        response = client.post(
            ROUTE, json=BODY, headers={k: v for k, v in HEADERS.items() if k != removed}
        )
    assert response.status_code in {401, 403} and not service.calls
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "error,status",
    [(AccessDeniedError(), 403), (ConflictError(), 409), (DependencyUnavailableError(), 503)],
)
def test_application_errors_keep_safe_problem_contract(
    error: ApplicationError, status: int
) -> None:
    service = MockHumanAdmitter()
    service.error = error
    with client_for(service) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["requestId"]


def test_parsed_uuid_scope_is_canonical_in_retry_context() -> None:
    service = MockHumanAdmitter()
    organization = UUID("abcdefab-abcd-4bcd-8bcd-abcdefabcdef")
    with client_for(service) as client:
        response = client.post(
            f"/v1/organizations/{str(organization).upper()}/human-admissions",
            json=BODY,
            headers=HEADERS,
        )
    assert response.status_code == 201
    command, context = service.calls[0]
    assert command.organization_id.value == organization
    assert context.requested_route == f"/v1/organizations/{organization}/human-admissions"
