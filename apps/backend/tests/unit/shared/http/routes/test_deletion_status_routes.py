"""Exercise the real adapter/core with private observations, not deletion or provider effects."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_facts_dto import (
    DeletionStatusFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.protocols.deletion_status_facts_reader import (
    DeletionStatusFactsReader,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.services.deletion_status_authorization_service import (
    DeletionStatusAuthorizationService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.handlers.human_oauth_credential_error_handler import (
    register_human_oauth_credential_error_handler,
)
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_obligation_provenance_dto import (
    DeletionStatusObligationProvenanceDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.deletion_status_lookup import (
    DeletionStatusLookup,
)
from inframeld_backend.shared.application.protocols.deletion_status_projection_reader import (
    DeletionStatusProjectionReader,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.services.deletion_status_read_service import (
    DeletionStatusReadService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.mappers.deletion_status_mapper import DeletionStatusMapper
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.http.routes.deletion_status_routes import (
    create_deletion_status_router,
)
from inframeld_backend.shared.http.types.deletion_status_response import DeletionStatusResponse

PATH = "/v1/deletions/status"
NOW = datetime(2030, 5, 10, tzinfo=UTC)
STARTED = NOW - timedelta(days=5)
OPERATION = OperationId("original-deletion")
ACTOR = Principal(
    PrincipalId(UUID(int=1)),
    OrganizationId(UUID(int=2)),
    PrincipalKind.HUMAN,
    PrincipalStatus.ACTIVE,
)
COOKIE = {"Cookie": "ory_kratos_session=fixture-cookie"}
BEARER = {"Authorization": "Bearer fixture-token"}
PRIVATE_VALUE = "PRIVATE_OWNER_VALUE_MUST_NOT_ESCAPE"
BINDING = DeletionStatusBindingDTO(
    OPERATION,
    RequestId(UUID(int=3)),
    InstallationId(UUID(int=123)),
    ACTOR.organization_id,
    ProjectId(UUID(int=4)),
    ACTOR.id,
    HttpMethod.DELETE,
    "/v1/original-project-deletion",
    IdempotencyKey(PRIVATE_VALUE),
    RequestFingerprint(b"F" * 32),
    OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
    ActionId("delete-project"),
    NOW - timedelta(days=10),
    30,
    "ADR-0117/PD-KNOWLEDGE-02:v1",
)
OBLIGATION = DeletionStatusObligationProvenanceDTO(
    UUID(int=5),
    OPERATION,
    BINDING.installation_id,
    BINDING.organization_id,
    BINDING.project_id,
    ACTOR.id,
    NOW - timedelta(minutes=1),
    1,
)
ACTIVE = DeletionStatusObservationDTO(
    BINDING,
    NOW,
    owner_revision=1,
    owner_observed_at=NOW - timedelta(minutes=1),
    job_status=JobStatus.RUNNING,
    admission_confirmed=True,
    access_blocked=True,
    unfinished_obligation=OBLIGATION,
)


class Scenario:
    """Supply controlled authentication/source facts while retaining the production core."""

    def __init__(self) -> None:
        self.access = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.browser())
        self.facts = DeletionStatusFactsDTO(
            BINDING.installation_id,
            ACTOR,
            False,
            HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(1)),
        )
        self.observation: DeletionStatusObservationDTO | None = ACTIVE
        self.events: list[str] = []
        self.queries: list[GetDeletionStatusQuery] = []
        self.projection_reads = 0
        self.failure: Exception | None = None
        self.block = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    @asynccontextmanager
    async def open_lookup(self) -> AsyncGenerator[DeletionStatusLookup]:
        self.events.append("open")
        try:
            core = DeletionStatusReadService(
                DeletionStatusAuthorizationService(MockFacts(self)), MockProjection(self)
            )
            yield RecordingLookup(self, core)
        finally:
            self.events.append("close")


class MockBrowserAuthenticator(HumanSessionAuthenticator):
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value != "fixture-cookie":
            raise AuthenticationRequiredError()
        return self.scenario.access


class MockBearerAuthenticator(HumanAccessTokenAuthenticator):
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    @override
    async def authenticate(self, credential: HumanAccessTokenCredential | None) -> AccessContextDTO:
        if credential is None or credential.value != "fixture-token":
            raise AuthenticationRequiredError()
        return replace(
            self.scenario.access, authentication_evidence=MockAuthenticationEvidence.human_oauth()
        )


class MockFacts(DeletionStatusFactsReader):
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    @override
    async def read(self, *, access: AccessContextDTO) -> DeletionStatusFactsDTO | None:
        return self.scenario.facts


class MockProjection(DeletionStatusProjectionReader):
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    @override
    async def read(
        self, *, authorization: DeletionStatusAuthorizationDTO
    ) -> DeletionStatusObservationDTO | None:
        self.scenario.projection_reads += 1
        return self.scenario.observation


class RecordingLookup(DeletionStatusLookup):
    def __init__(self, scenario: Scenario, core: DeletionStatusLookup) -> None:
        self.scenario = scenario
        self.core = core

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: GetDeletionStatusQuery
    ) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO:
        self.scenario.events.append("lookup")
        self.scenario.queries.append(query)
        if self.scenario.failure is not None:
            raise self.scenario.failure
        if self.scenario.block:
            self.scenario.started.set()
            await self.scenario.release.wait()
        return await self.core.lookup(access=access, query=query)


def app_for(scenario: Scenario) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    register_human_oauth_credential_error_handler(app)
    configure_problem_openapi(app)
    app.include_router(
        create_deletion_status_router(
            HumanSessionDependency(
                MockBrowserAuthenticator(scenario),
                CSRFProtectionDependency(()),
                access_token_authenticator=MockBearerAuthenticator(scenario),
            ),
            scenario.open_lookup,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return app


def settled() -> DeletionStatusObservationDTO:
    return replace(
        ACTIVE,
        owner_revision=2,
        owner_observed_at=STARTED,
        job_status=JobStatus.SUCCEEDED,
        application_shutdown_complete=True,
        physical_cleanup_complete=True,
        unfinished_obligation=None,
        retention_started_at=STARTED,
        expires_at=STARTED + timedelta(days=30),
    )


@pytest.mark.parametrize("headers", [COOKIE, BEARER])
def test_retained_response_preserves_unknowns_and_excludes_private_fields(
    headers: dict[str, str],
) -> None:
    scenario = Scenario()
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "retained",
        "operationId": OPERATION.value,
        "jobState": "running",
        "admissionConfirmed": True,
        "accessBlocked": True,
        "applicationShutdownComplete": None,
        "physicalCleanupComplete": None,
        "retentionExpiresAt": None,
    }
    assert PRIVATE_VALUE not in response.text
    assert str(BINDING.project_id.value) not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "location" not in response.headers
    assert scenario.events == ["open", "lookup", "close"]


def test_settled_observation_keeps_original_expiry_on_repeated_reads() -> None:
    scenario = Scenario()
    scenario.observation = settled()
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        first = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
        second = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["retentionExpiresAt"] == "2030-06-04T00:00:00Z"
    assert first.json()["physicalCleanupComplete"] is True
    assert scenario.events == ["open", "lookup", "close"] * 2
    assert scenario.observation == settled()


@pytest.mark.parametrize(
    "observation",
    [
        None,
        DeletionStatusObservationDTO(BINDING, NOW),
        replace(settled(), observed_at=STARTED + timedelta(days=30)),
    ],
)
def test_absent_binding_only_and_expired_observations_are_exactly_unresolved(
    observation: DeletionStatusObservationDTO | None,
) -> None:
    scenario = Scenario()
    scenario.observation = observation
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
    assert response.status_code == 200
    assert response.json() == {"outcome": "unresolved"}
    assert response.headers["cache-control"] == "no-store"


def test_another_eligible_human_cannot_observe_original_initiator_history() -> None:
    scenario = Scenario()
    other = replace(ACTOR, id=PrincipalId(UUID(int=99)))
    scenario.access = replace(scenario.access, actor_principal_id=other.id)
    scenario.facts = replace(scenario.facts, principal=other)
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
    assert response.status_code == 200
    assert response.json() == {"outcome": "unresolved"}


@pytest.mark.parametrize("operation", [" op/with%?x=1&part=two ", "a" * 128])
def test_opaque_reference_reaches_core_unchanged(operation: str) -> None:
    scenario = Scenario()
    scenario.observation = None
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": operation}, headers=COOKIE)
    assert response.status_code == 200
    assert scenario.queries == [GetDeletionStatusQuery(OperationId(operation))]


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?operationId=",
        "?operationId=%20%20%20",
        "?operationId=" + "a" * 129,
        "?operationId=one&operationId=one",
        "?operationId=one&operationId=two",
        "?operationId=one&actor=" + PRIVATE_VALUE,
        "?operationId=one&projectId=" + PRIVATE_VALUE,
    ],
)
def test_invalid_query_never_opens_lookup_or_reflects_submitted_scope(query: str) -> None:
    scenario = Scenario()
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH + query, headers=COOKIE)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert PRIVATE_VALUE not in response.text
    assert "operationId" not in response.json()
    assert scenario.events == []


@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 401),
        ({"Cookie": "ory_kratos_session=invalid-cookie"}, 401),
        ({"Authorization": "Bearer invalid-token"}, 401),
        ({"Authorization": "Bearer ifm_app_not-a-human"}, 401),
        ({"Authorization": "Basic invalid"}, 401),
        (COOKIE | BEARER, 400),
    ],
)
def test_rejected_incoming_credentials_prevent_context_opening(
    headers: dict[str, str],
    status: int,
) -> None:
    scenario = Scenario()
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=headers)
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert scenario.events == []


@pytest.mark.parametrize("status", [PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED])
def test_current_ineligible_human_is_denied_without_reading_projection(
    status: PrincipalStatus,
) -> None:
    scenario = Scenario()
    scenario.facts = replace(scenario.facts, principal=replace(ACTOR, status=status))
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"
    assert scenario.projection_reads == 0
    assert scenario.events == ["open", "lookup", "close"]


def test_fresh_read_does_not_reuse_authority_after_recovery_begins() -> None:
    scenario = Scenario()
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        first = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
        scenario.facts = replace(scenario.facts, has_pending_recovery=True)
        second = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
    assert first.status_code == 200
    assert second.status_code == 403
    assert scenario.projection_reads == 1


def test_stale_oauth_generation_retains_the_existing_invalid_token_challenge() -> None:
    scenario = Scenario()
    scenario.facts = replace(
        scenario.facts,
        oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(2)),
    )
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=BEARER)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="inframeld", error="invalid_token"'
    assert response.headers["cache-control"] == "no-store"
    assert scenario.projection_reads == 0
    assert scenario.events[-1] == "close"


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (DependencyUnavailableError(PRIVATE_VALUE), 503, "dependency_unavailable"),
        (RuntimeError(PRIVATE_VALUE), 500, "internal_error"),
    ],
)
def test_lookup_failures_close_context_and_remain_safe_problems(
    failure: Exception,
    status: int,
    code: str,
) -> None:
    scenario = Scenario()
    scenario.failure = failure
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert PRIVATE_VALUE not in response.text
    assert "operationId" not in response.json()
    assert scenario.events == ["open", "lookup", "close"]


def test_response_mapping_occurs_after_context_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario()
    original = DeletionStatusMapper.to_response

    def mapping(
        result: RetainedDeletionStatusDTO | UnresolvedOperationDTO,
    ) -> DeletionStatusResponse:
        assert scenario.events[-1] == "close"
        return original(result)

    monkeypatch.setattr(DeletionStatusMapper, "to_response", staticmethod(mapping))
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
    assert response.status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_unsupported_method_retains_405_without_json_framing_or_lookup(method: str) -> None:
    scenario = Scenario()
    with TestClient(app_for(scenario), raise_server_exceptions=False) as client:
        response = client.request(method, PATH, params={"operationId": OPERATION.value})
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.headers["cache-control"] == "no-store"
    assert scenario.events == []


@pytest.mark.asyncio
async def test_request_cancellation_closes_the_supplied_context() -> None:
    scenario = Scenario()
    scenario.block = True
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app_for(scenario)), base_url="http://fixture"
    ) as client:
        request = asyncio.create_task(
            client.get(PATH, params={"operationId": OPERATION.value}, headers=COOKIE)
        )
        try:
            await asyncio.wait_for(scenario.started.wait(), timeout=1)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        finally:
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)
    assert scenario.events == ["open", "lookup", "close"]


def test_mounted_native_contract_describes_query_union_and_problem_media() -> None:
    schema = app_for(Scenario()).openapi()
    operation = schema["paths"][PATH]["get"]
    assert operation["operationId"] == "getDeletionStatus"
    parameter = next(item for item in operation["parameters"] if item["name"] == "operationId")
    assert parameter["in"] == "query" and parameter["required"] is True
    assert parameter["schema"]["minLength"] == 1
    assert parameter["schema"]["maxLength"] == 128
    success = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success == {"$ref": "#/components/schemas/DeletionStatusResponse"}
    union = schema["components"]["schemas"]["DeletionStatusResponse"]
    assert union["discriminator"]["propertyName"] == "outcome"
    for status in ("400", "401", "403", "422", "503"):
        assert set(operation["responses"][status]["content"]) == {"application/problem+json"}
    properties = schema["components"]["schemas"]["RetainedDeletionStatusResponse"]["properties"]
    assert set(properties) == {
        "outcome",
        "operationId",
        "jobState",
        "admissionConfirmed",
        "accessBlocked",
        "applicationShutdownComplete",
        "physicalCleanupComplete",
        "retentionExpiresAt",
    }
