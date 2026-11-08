"""Exercise show-once issuance, exact input and existing credential protections over HTTP."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.protocols.application_key_issuer import (
    ApplicationKeyIssuer,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.application_key_issuance_routes import (
    create_application_key_issuance_router,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

PROJECT, APP = ProjectId(UUID(int=3)), PrincipalId(UUID(int=8))
HUMAN = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
APPLICATION = AccessContextDTO(APP, MockAuthenticationEvidence.application_key())
NOW = datetime(2030, 1, 1, tzinfo=UTC)
CREDENTIAL = ApplicationKeyCredential(f"ifm_app_{UUID(int=10)}_" + "A" * 43)
ROUTE = f"/v1/projects/{PROJECT.value}/application-accounts/{APP.value}/keys"
BODY = {"allowedAdapters": ["mcp", "http"], "expectedAccessRevision": 7}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "issue-original",
}


class MockIssuer(ApplicationKeyIssuer):
    def __init__(self, *, replay: bool = False, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[
            tuple[AccessContextDTO, IssueApplicationKeyCommand, IdempotencyContextDTO]
        ] = []
        self.result = ApplicationKeyIssueResultDTO(
            ApplicationKeyIssuanceRecordDTO(
                operation_id=OperationId("issued-original"),
                organization_id=OrganizationId(UUID(int=2)),
                installation_id=InstallationId(UUID(int=4)),
                issuer_principal_id=HUMAN.actor_principal_id,
                access_revision=8,
                metadata=ApplicationKeyMetadataDTO(
                    CREDENTIAL.key_id,
                    APP,
                    PROJECT,
                    (ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP),
                    NOW,
                    NOW + timedelta(days=90),
                    None,
                ),
            ),
            CompletedSynchronousOperationDTO(
                OperationId("issued-original"),
                not replay,
                OperationReplayKind.ISSUED_SECRET,
                NOW + timedelta(days=1),
            ),
            None if replay else CREDENTIAL,
        )

    @override
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyIssueResultDTO:
        self.calls.append((access, command, context))
        if self.failure is not None:
            raise self.failure
        return self.result


class MockHumanAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    def __init__(self) -> None:
        self.calls: list[BrowserSessionCredential | HumanAccessTokenCredential | None] = []

    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        self.calls.append(credential)
        return (
            replace(HUMAN, authentication_evidence=MockAuthenticationEvidence.human_oauth())
            if isinstance(credential, HumanAccessTokenCredential)
            else HUMAN
        )


def client_for(
    issuer: MockIssuer,
    human: MockHumanAuthenticator | None = None,
    application: MockApplicationAuthenticator | None = None,
) -> TestClient:
    human = human or MockHumanAuthenticator()
    application = application or MockApplicationAuthenticator(APPLICATION)

    @asynccontextmanager
    async def open_issuer() -> AsyncGenerator[ApplicationKeyIssuer]:
        yield issuer

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_application_key_issuance_router(
            ProductAccessDependency(
                human,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=human,
                application_authenticator=application,
            ),
            open_issuer,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("replay", [False, True])
def test_issue_returns_typed_first_or_safe_replay_and_preserves_original_inputs(
    replay: bool,
) -> None:
    issuer = MockIssuer(replay=replay)
    with client_for(issuer) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 201
    data = response.json()
    assert set(data) == {
        "operationId",
        "accessRevision",
        "idempotencyExpiresAt",
        "metadata",
        "secretAvailable",
    } | (set() if replay else {"key"})
    assert data["secretAvailable"] is not replay
    assert ("key" in data) is not replay
    if not replay:
        assert data["key"] == CREDENTIAL.value
    assert data["metadata"] == {
        "keyId": str(CREDENTIAL.key_id.value),
        "applicationPrincipalId": str(APP.value),
        "projectId": str(PROJECT.value),
        "prefix": "ifm_app_",
        "allowedAdapters": ["mcp", "http"],
        "createdAt": "2030-01-01T00:00:00Z",
        "expiresAt": "2030-04-01T00:00:00Z",
        "revokedAt": None,
    }
    assert response.headers["cache-control"] == "no-store" and response.headers["x-request-id"]
    assert issuer.calls == [
        (
            HUMAN,
            IssueApplicationKeyCommand(
                PROJECT, APP, (ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP), 7
            ),
            IdempotencyContextDTO(HttpMethod.POST, ROUTE, issuer.calls[0][2].key),
        )
    ]
    assert issuer.calls[0][2].key.value == "issue-original"
    assert issuer.calls[0][1].expires_in_seconds is None


def test_explicit_whole_lifetime_and_human_bearer_need_no_cookie_csrf() -> None:
    issuer, human, application = (
        MockIssuer(),
        MockHumanAuthenticator(),
        MockApplicationAuthenticator(APPLICATION),
    )
    with client_for(issuer, human, application) as client:
        response = client.post(
            ROUTE,
            json={**BODY, "expiresInSeconds": 60},
            headers={
                "Authorization": "Bearer controlled-human",
                "Idempotency-Key": "issue-original",
            },
        )
    assert response.status_code == 201
    assert issuer.calls[0][1].expires_in_seconds == 60
    assert isinstance(
        issuer.calls[0][0].authentication_evidence, type(MockAuthenticationEvidence.human_oauth())
    )
    assert len(human.calls) == 1 and application.calls == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"allowedAdapters": []},
        {"allowedAdapters": ["http", "http"]},
        {"allowedAdapters": ["other"]},
        {"allowedAdapters": "http"},
        {"expiresInSeconds": None},
        {"expiresInSeconds": True},
        {"expiresInSeconds": 1.5},
        {"expiresInSeconds": "60"},
        {"expiresInSeconds": 0},
        {"expiresInSeconds": -1},
        {"expiresInSeconds": 9007199254740992},
        {"expectedAccessRevision": None},
        {"expectedAccessRevision": True},
        {"expectedAccessRevision": 1.5},
        {"expectedAccessRevision": "7"},
        {"expectedAccessRevision": -1},
        {"expectedAccessRevision": 9007199254740992},
        {"audience": "https://untrusted.test"},
        {"key": "must-not-be-echoed"},
    ],
)
def test_invalid_or_unknown_input_is_rejected_before_issuance(patch: dict[str, object]) -> None:
    issuer = MockIssuer()
    with client_for(issuer) as client:
        response = client.post(ROUTE, json={**BODY, **patch}, headers=HEADERS)
    assert response.status_code == 422
    assert (
        issuer.calls == []
        and CREDENTIAL.value not in response.text
        and "must-not-be-echoed" not in response.text
    )


@pytest.mark.parametrize("missing", ["Cookie", "Origin", "X-Inframeld-CSRF", "Idempotency-Key"])
def test_cookie_write_requires_identity_csrf_origin_and_original_key(missing: str) -> None:
    issuer = MockIssuer()
    with client_for(issuer) as client:
        response = client.post(
            ROUTE, json=BODY, headers={k: v for k, v in HEADERS.items() if k != missing}
        )
    assert response.status_code == (
        401 if missing == "Cookie" else 422 if missing == "Idempotency-Key" else 403
    )
    assert issuer.calls == []


def test_competing_credentials_stop_before_authentication_or_issuance() -> None:
    issuer, human, application = (
        MockIssuer(),
        MockHumanAuthenticator(),
        MockApplicationAuthenticator(APPLICATION),
    )
    with client_for(issuer, human, application) as client:
        response = client.post(
            ROUTE, json=BODY, headers={**HEADERS, "Authorization": "Bearer controlled-human"}
        )
    assert response.status_code == 400
    assert human.calls == [] and application.calls == 0 and issuer.calls == []


def test_supported_application_authentication_can_receive_human_only_denial_without_fallback() -> (
    None
):
    issuer, human, application = (
        MockIssuer(failure=AccessDeniedError()),
        MockHumanAuthenticator(),
        MockApplicationAuthenticator(APPLICATION),
    )
    with client_for(issuer, human, application) as client:
        response = client.post(
            ROUTE,
            json=BODY,
            headers={
                "Authorization": "Bearer " + CREDENTIAL.value,
                "Idempotency-Key": "issue-original",
            },
        )
    assert response.status_code == 403
    assert human.calls == [] and application.calls == 1 and issuer.calls[0][0] == APPLICATION


@pytest.mark.parametrize(
    "failure,status",
    [
        (AccessDeniedError(), 403),
        (ResourceNotFoundError(), 404),
        (StaleRevisionError(), 409),
        (ConflictError(), 409),
        (InvalidInputError(), 422),
        (DependencyUnavailableError(), 503),
    ],
)
def test_handled_failures_keep_safe_status_correlation_and_no_store(
    failure: Exception, status: int
) -> None:
    issuer = MockIssuer(failure=failure)
    with client_for(issuer) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == status
    assert len(issuer.calls) == 1
    assert response.headers["cache-control"] == "no-store" and response.headers["x-request-id"]
    assert CREDENTIAL.value not in response.text and "key" not in response.json()


@pytest.mark.parametrize(
    "kind,status",
    [
        ("query", 422),
        ("duplicates", 422),
        ("nonfinite", 422),
        ("array", 422),
        ("wrong-content", 415),
        ("too-large", 413),
    ],
)
def test_existing_bounded_account_parser_rejects_ambiguous_or_unbounded_input(
    kind: str, status: int
) -> None:
    issuer = MockIssuer()
    body = '{"allowedAdapters":["http"],"expectedAccessRevision":7}'
    headers = {**HEADERS, "Content-Type": "application/json"}
    path = ROUTE + ("?expiresInSeconds=60" if kind == "query" else "")
    if kind == "duplicates":
        body = '{"allowedAdapters":["http"],"expectedAccessRevision":7,"expectedAccessRevision":7}'
    if kind == "nonfinite":
        body = '{"allowedAdapters":["http"],"expectedAccessRevision":NaN}'
    if kind == "array":
        body = "[]"
    if kind == "wrong-content":
        headers["Content-Type"] = "text/plain"
    if kind == "too-large":
        body = '{"padding":"' + "x" * 32768 + '"}'
    with client_for(issuer) as client:
        response = client.post(path, content=body, headers=headers)
    assert response.status_code == status and issuer.calls == []


def test_native_issue_operation_declares_strict_request_and_discriminated_delivery() -> None:
    schema = TestClient(create_app()).get("/v1/openapi.json").json()
    path = "/v1/projects/{project_id}/application-accounts/{application_principal_id}/keys"
    assert "post" in schema["paths"][path], "Native application-key issuance is not registered."
    operation = schema["paths"][path]["post"]
    assert operation["operationId"] == "issueApplicationKey"
    assert operation["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
    models = schema["components"]["schemas"]
    request = models["ApplicationKeyIssueRequest"]
    assert request["additionalProperties"] is False
    assert set(request["required"]) == {"allowedAdapters", "expectedAccessRevision"}
    assert request["properties"]["allowedAdapters"]["uniqueItems"] is True
    for field in ("expectedAccessRevision", "expiresInSeconds"):
        bound = request["properties"][field]
        assert bound["type"] == "integer" and type(bound["maximum"]) is int
        assert bound["maximum"] == 9007199254740991
    assert (
        models["ApplicationKeyIssueResponse"]["discriminator"]["propertyName"] == "secretAvailable"
    )
    first, replay = (
        models["ApplicationKeyFirstDeliveryResponse"],
        models["ApplicationKeyIssuanceReplayResponse"],
    )
    assert "key" in first["required"] and "key" not in replay["properties"]
    assert first["additionalProperties"] is False and replay["additionalProperties"] is False
