"""Exercise future-upload defaults without crossing the persistence or provider boundary."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import override

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
)
from tests.support.mock_project_upload_defaults import (
    NEW,
    A,
    B,
    C,
    MockUploadDefaultFactsReader,
    MockUploadDefaultRepository,
    MockUploadDefaultTransactions,
)

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_upload_default_change_result_dto import (
    ProjectUploadDefaultChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_dto import (
    ProjectUploadDefaultDTO,
)
from inframeld_backend.access.application.dtos.upload_default_group_facts_dto import (
    UploadDefaultGroupFactsDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_upload_default_changer import (
    ProjectUploadDefaultChanger,
)
from inframeld_backend.access.application.protocols.project_upload_default_reader import (
    ProjectUploadDefaultReader,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)
from inframeld_backend.access.application.services.project_upload_default_fingerprint_service import (
    ProjectUploadDefaultFingerprintService,
)
from inframeld_backend.access.application.services.project_upload_default_service import (
    ProjectUploadDefaultService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.project_upload_default_routes import (
    create_project_upload_default_router,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

ROUTE = f"/v1/projects/{PROJECT_ID.value}/upload-defaults"
BODY = {"groupIds": [str(B.value)], "expectedAccessRevision": 7}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "upload-original",
}
APPLICATION = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.application_key())


class MockHumanAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    def __init__(self) -> None:
        self.calls: list[BrowserSessionCredential | HumanAccessTokenCredential | None] = []

    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        self.calls.append(credential)
        return (
            replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
            if isinstance(credential, HumanAccessTokenCredential)
            else ACCESS
        )


class MockDefaultOperations(ProjectUploadDefaultReader, ProjectUploadDefaultChanger):
    def __init__(self) -> None:
        self.reads: list[tuple[AccessContextDTO, GetProjectUploadDefaultQuery]] = []
        self.writes: list[
            tuple[AccessContextDTO, SetProjectUploadDefaultCommand, IdempotencyContextDTO]
        ] = []
        self.current = ProjectUploadDefaultDTO(ORGANIZATION_ID, PROJECT_ID, 9, UploadAudience((C,)))
        self.original = ProjectUploadDefaultChangeResultDTO(
            ProjectUploadDefaultDTO(ORGANIZATION_ID, PROJECT_ID, 8, NEW), SAVED_RESULT
        )
        self.failure: Exception | None = None

    @override
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectUploadDefaultQuery
    ) -> ProjectUploadDefaultDTO:
        self.reads.append((access, query))
        if self.failure is not None:
            raise self.failure
        return self.current

    @override
    async def set(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectUploadDefaultCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectUploadDefaultChangeResultDTO:
        self.writes.append((access, command, context))
        if self.failure is not None:
            raise self.failure
        return self.original


def client_for(
    service: MockDefaultOperations | ProjectUploadDefaultService,
    human: MockHumanAuthenticator | None = None,
    application: MockApplicationAuthenticator | None = None,
) -> TestClient:
    human = human or MockHumanAuthenticator()
    application = application or MockApplicationAuthenticator(APPLICATION)

    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[ProjectUploadDefaultReader]:
        yield service

    @asynccontextmanager
    async def open_changer() -> AsyncGenerator[ProjectUploadDefaultChanger]:
        yield service

    app = FastAPI()
    register_error_handlers(app)
    configure_problem_openapi(app)
    app.include_router(
        create_project_upload_default_router(
            ProductAccessDependency(
                human,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=human,
                application_authenticator=application,
            ),
            open_reader,
            open_changer,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def test_current_read_and_historical_put_receipt_are_distinct_and_after_only() -> None:
    service = MockDefaultOperations()
    with client_for(service) as client:
        current = client.get(ROUTE, headers=HEADERS)
        replay = client.put(ROUTE, json=BODY, headers=HEADERS)
    assert current.status_code == replay.status_code == 200
    assert current.json() == {
        "projectId": str(PROJECT_ID.value),
        "accessRevision": 9,
        "groupIds": [str(C.value)],
    }
    assert replay.json() == {
        "projectId": str(PROJECT_ID.value),
        "accessRevision": 8,
        "groupIds": [str(B.value)],
        "operationId": SAVED_RESULT.operation_id.value,
        "idempotencyExpiresAt": SAVED_RESULT.expires_at.isoformat().replace("+00:00", "Z"),
    }
    assert str(A.value) not in replay.text
    assert "organizationId" not in replay.json() and "beforeGroupIds" not in replay.json()
    assert service.reads == [(ACCESS, GetProjectUploadDefaultQuery(PROJECT_ID))]
    access, command, context = service.writes[0]
    assert access == ACCESS and command == SetProjectUploadDefaultCommand(PROJECT_ID, NEW, 7)
    assert context == IdempotencyContextDTO(HttpMethod.PUT, ROUTE, context.key)
    assert context.key.value == "upload-original"
    assert current.headers["cache-control"] == replay.headers["cache-control"] == "no-store"


def test_valid_unconfigured_project_is_null_not_an_empty_group_set() -> None:
    service = MockDefaultOperations()
    service.current = replace(service.current, audience=None)
    with client_for(service) as client:
        response = client.get(ROUTE, headers=HEADERS)
    assert response.status_code == 200 and response.json()["groupIds"] is None


def test_canonical_group_order_and_safe_revision_edges_survive_mapping() -> None:
    service = MockDefaultOperations()
    with client_for(service) as client:
        for revision in [0, 9007199254740991]:
            response = client.put(
                ROUTE,
                json={"groupIds": [str(C.value), str(B.value)], "expectedAccessRevision": revision},
                headers=HEADERS,
            )
            assert response.status_code == 200
            assert service.writes[-1][1].audience == UploadAudience((B, C))
            assert service.writes[-1][1].expected_access_revision == revision


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"groupIds": None, "expectedAccessRevision": 7},
        {"groupIds": [], "expectedAccessRevision": 7},
        {"groupIds": [str(B.value), str(B.value)], "expectedAccessRevision": 7},
        {"groupIds": ["invalid"], "expectedAccessRevision": 7},
        {"groupIds": [1], "expectedAccessRevision": 7},
        {**BODY, "expectedAccessRevision": True},
        {**BODY, "expectedAccessRevision": 1.5},
        {**BODY, "expectedAccessRevision": "7"},
        {**BODY, "expectedAccessRevision": -1},
        {**BODY, "expectedAccessRevision": 9007199254740992},
        {**BODY, "expectedAccessRevision": None},
        {**BODY, "audience": "private-must-not-echo"},
    ],
)
def test_strict_write_body_never_calls_service_on_invalid_input(body: dict[str, object]) -> None:
    service = MockDefaultOperations()
    with client_for(service) as client:
        response = client.put(ROUTE, json=body, headers=HEADERS)
    assert response.status_code == 422 and service.writes == []
    assert response.headers["cache-control"] == "no-store"
    assert "private-must-not-echo" not in response.text


@pytest.mark.parametrize(
    "method,kind,status",
    [
        ("GET", "query", 422),
        ("GET", "body", 422),
        ("PUT", "query", 422),
        ("PUT", "duplicate", 422),
        ("PUT", "nonfinite", 422),
        ("PUT", "array", 422),
        ("PUT", "invalid-utf8", 422),
        ("PUT", "wrong-content", 415),
        ("PUT", "oversized", 413),
    ],
)
def test_exact_bounded_http_framing_rejects_ambiguous_inputs(
    method: str, kind: str, status: int
) -> None:
    service = MockDefaultOperations()
    content = b"{}" if kind == "body" else b'{"groupIds":[],"expectedAccessRevision":7}'
    if kind == "duplicate":
        content = b'{"groupIds":[],"groupIds":[],"expectedAccessRevision":7}'
    if kind == "nonfinite":
        content = b'{"groupIds":[],"expectedAccessRevision":NaN}'
    if kind == "array":
        content = b"[]"
    if kind == "invalid-utf8":
        content = bytes([255])
    if kind == "oversized":
        content = b" " * 32769
    with client_for(service) as client:
        response = client.request(
            method,
            ROUTE + ("?groupIds=ignored" if kind == "query" else ""),
            content=content if method == "PUT" or kind == "body" else None,
            headers=HEADERS
            | {"Content-Type": "text/plain" if kind == "wrong-content" else "application/json"},
        )
    assert response.status_code == response.json()["status"] == status
    assert response.headers["cache-control"] == "no-store"
    assert service.reads == service.writes == []


@pytest.mark.parametrize(
    "missing,status",
    [("Cookie", 401), ("Origin", 403), ("X-Inframeld-CSRF", 403), ("Idempotency-Key", 422)],
)
def test_cookie_mutation_requires_identity_origin_csrf_and_original_key(
    missing: str, status: int
) -> None:
    service = MockDefaultOperations()
    with client_for(service) as client:
        response = client.put(
            ROUTE, json=BODY, headers={k: v for k, v in HEADERS.items() if k != missing}
        )
    assert response.status_code == status and service.writes == []
    assert response.headers["cache-control"] == "no-store"


def test_foreign_origin_and_competing_credentials_fail_before_operation() -> None:
    service, human = MockDefaultOperations(), MockHumanAuthenticator()
    with client_for(service, human) as client:
        foreign = client.put(ROUTE, json=BODY, headers=HEADERS | {"Origin": "https://foreign.test"})
        assert foreign.status_code == 403 and service.writes == []
        calls = human.calls.copy()
        competing = client.get(ROUTE, headers=HEADERS | {"Authorization": "Bearer private-token"})
    assert competing.status_code == 400 and human.calls == calls and service.reads == []


def test_human_bearer_needs_no_cookie_csrf_and_passes_exact_evidence() -> None:
    service, human, application = (
        MockDefaultOperations(),
        MockHumanAuthenticator(),
        MockApplicationAuthenticator(APPLICATION),
    )
    with client_for(service, human, application) as client:
        response = client.put(
            ROUTE,
            json=BODY,
            headers={"Authorization": "Bearer private-token", "Idempotency-Key": "upload-original"},
        )
    assert response.status_code == 200 and application.calls == 0
    assert service.writes[0][0].authentication_evidence == MockAuthenticationEvidence.human_oauth()
    assert len(human.calls) == 1


@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize(
    "failure,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (StaleRevisionError(), 409, "stale_revision"),
        (ConflictError(), 409, "conflict"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_current_scope_and_replay_errors_keep_exact_problem_details(
    method: str, failure: Exception, status: int, code: str
) -> None:
    service = MockDefaultOperations()
    service.failure = failure
    with client_for(service) as client:
        response = client.request(
            method, ROUTE, json=BODY if method == "PUT" else None, headers=HEADERS
        )
    assert response.status_code == response.json()["status"] == status
    assert response.json()["code"] == code
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    assert len(service.reads) + len(service.writes) == 1


def test_actual_application_openapi_declares_both_native_operations_and_safe_models() -> None:
    schema = create_app().openapi()
    path = "/v1/projects/{project_id}/upload-defaults"
    assert path in schema["paths"], "Upload-default operations are not registered."
    get, put = schema["paths"][path]["get"], schema["paths"][path]["put"]
    assert get["operationId"] == "getProjectUploadDefaults"
    assert put["operationId"] == "setProjectUploadDefaults"
    assert get["security"] == put["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
    models = schema["components"]["schemas"]
    request, response, changed = (
        models["ProjectUploadDefaultRequest"],
        models["ProjectUploadDefaultResponse"],
        models["ProjectUploadDefaultChangeResponse"],
    )
    assert (
        request["additionalProperties"] is False
        and response["additionalProperties"] is False
        and changed["additionalProperties"] is False
    )
    assert set(request["required"]) == {"groupIds", "expectedAccessRevision"}
    assert set(request["properties"]) == {"groupIds", "expectedAccessRevision"}
    assert request["properties"]["expectedAccessRevision"]["maximum"] == 9007199254740991
    assert request["properties"]["groupIds"]["minItems"] == 1
    assert set(response["properties"]) == {"projectId", "accessRevision", "groupIds"}
    assert set(changed["properties"]) == {
        "projectId",
        "accessRevision",
        "groupIds",
        "operationId",
        "idempotencyExpiresAt",
    }
    for operation in (get, put):
        for code in ["400", "401", "403", "404", "409", "422", "503"]:
            assert operation["responses"][code]["content"]["application/problem+json"]["schema"][
                "$ref"
            ].endswith("/ProblemDetails")


@pytest.fixture
def core_setup() -> tuple[
    ProjectUploadDefaultService,
    MockUploadDefaultFactsReader,
    MockUploadDefaultRepository,
    MockOperationIdempotency,
    MockUploadDefaultTransactions,
    list[str],
]:
    """Exercise the real application operation with controlled current-fact and transaction ports."""
    events: list[str] = []
    facts, repo, idem, tx = (
        MockUploadDefaultFactsReader(events),
        MockUploadDefaultRepository(events),
        MockOperationIdempotency(events),
        MockUploadDefaultTransactions(events),
    )
    idem.result = NEW_RESERVATION
    service = ProjectUploadDefaultService(
        transaction_manager=tx,
        default_facts_reader=facts,
        default_repository=repo,
        operation_idempotency=idem,
        default_fingerprint_service=ProjectUploadDefaultFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
        ),
    )
    return service, facts, repo, idem, tx, events


type CoreSetup = tuple[
    ProjectUploadDefaultService,
    MockUploadDefaultFactsReader,
    MockUploadDefaultRepository,
    MockOperationIdempotency,
    MockUploadDefaultTransactions,
    list[str],
]


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_application_credential_is_denied_by_real_human_only_operation(
    core_setup: CoreSetup, method: str
) -> None:
    service, facts, repo, idem, _, _ = core_setup
    assert facts.facts is not None
    facts.facts = replace(
        facts.facts,
        action=replace(
            facts.facts.action,
            principal=replace(facts.facts.action.principal, kind=PrincipalKind.APPLICATION),
        ),
    )
    human, application = MockHumanAuthenticator(), MockApplicationAuthenticator(APPLICATION)
    with client_for(service, human, application) as client:
        response = client.request(
            method,
            ROUTE,
            json=BODY if method == "PUT" else None,
            headers={
                "Authorization": "Bearer ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43,
                "Idempotency-Key": "upload-original",
            },
        )
    assert response.status_code == 403 and response.json()["code"] == "access_denied"
    assert human.calls == [] and application.calls == 1
    assert idem.calls == 0 and repo.saved == []


@pytest.mark.parametrize("loss", ["project-action", "old-group", "new-group", "retained-group"])
def test_real_current_authority_is_checked_before_original_recovery(
    core_setup: CoreSetup, loss: str
) -> None:
    service, facts, repo, idem, _, events = core_setup
    assert facts.facts is not None
    idem.result = SAVED_RESULT
    if loss == "project-action":
        facts.facts = replace(
            facts.facts, action=replace(facts.facts.action, has_exact_action_grant=False)
        )
    else:
        group = B if loss == "new-group" else A
        facts.facts = replace(
            facts.facts,
            groups=tuple(
                replace(g, is_manager=False) if g.group_id == group else g
                for g in facts.facts.groups
            ),
        )
    body = (
        BODY
        if loss != "retained-group"
        else {"groupIds": [str(A.value), str(B.value)], "expectedAccessRevision": 7}
    )
    with client_for(service) as client:
        response = client.put(ROUTE, json=body, headers=HEADERS)
    assert response.status_code == 403 and response.json()["code"] == "access_denied"
    assert idem.calls == 0 and "original" not in events and repo.saved == []


def test_real_historical_replay_returns_b_without_overwriting_later_c(
    core_setup: CoreSetup,
) -> None:
    service, facts, repo, idem, _, events = core_setup
    assert facts.facts is not None
    facts.facts = replace(
        facts.facts,
        access_revision=99,
        audience=UploadAudience((C,)),
        groups=(
            UploadDefaultGroupFactsDTO(B, PROJECT_ID, True, True, False),
            UploadDefaultGroupFactsDTO(C, PROJECT_ID, True, True, False),
        ),
    )
    idem.result = SAVED_RESULT
    with client_for(service) as client:
        response = client.put(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 200 and response.json()["groupIds"] == [str(B.value)]
    assert response.json()["accessRevision"] == 8
    assert str(A.value) not in response.text and str(C.value) not in response.text
    assert events == [
        "begin",
        "lock-current",
        "reserve",
        "original",
        "commit-attempt",
        "commit-confirmed",
    ]
    assert repo.saved == [] and facts.facts.audience == UploadAudience((C,))


def test_real_fresh_equal_set_requires_review_revision_before_noop(core_setup: CoreSetup) -> None:
    service, facts, repo, idem, _, events = core_setup
    assert facts.facts is not None
    facts.facts = replace(
        facts.facts, groups=tuple(g for g in facts.facts.groups if g.group_id == A)
    )
    with client_for(service) as client:
        stale = client.put(
            ROUTE, json={"groupIds": [str(A.value)], "expectedAccessRevision": 6}, headers=HEADERS
        )
        assert stale.status_code == 409 and stale.json()["code"] == "stale_revision"
        assert repo.saved == [] and "rollback-requested" in events
        response = client.put(
            ROUTE,
            json={"groupIds": [str(A.value)], "expectedAccessRevision": 7},
            headers=HEADERS | {"Idempotency-Key": "fresh-noop"},
        )
    assert response.status_code == 200 and response.json()["accessRevision"] == 7
    assert response.json()["groupIds"] == [str(A.value)]
    assert (
        len(repo.saved) == 1 and repo.saved[0].before_revision == repo.saved[0].access_revision == 7
    )
    assert idem.calls == 2


@pytest.mark.parametrize("uncertain_commit", [False, True])
def test_real_rollback_and_unknown_commit_return_503_without_automatic_redispatch(
    core_setup: CoreSetup, uncertain_commit: bool
) -> None:
    service, _, repo, idem, tx, events = core_setup
    if uncertain_commit:
        tx.commit_ack_error = DependencyUnavailableError()
    else:
        repo.error = DependencyUnavailableError()
    with client_for(service) as client:
        response = client.put(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 503 and response.json()["code"] == "dependency_unavailable"
    assert response.headers["cache-control"] == "no-store" and idem.calls == 1
    assert ("commit-outcome-unknown" in events) is uncertain_commit
    assert ("rollback-requested" in events) is not uncertain_commit
