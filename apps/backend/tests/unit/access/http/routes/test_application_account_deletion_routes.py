"""Exercise private retirement transport without claiming stored credential or SQL proof."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl, ValidationError
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_project_metadata import (
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_deletion_facts_dto import (
    ApplicationAccountDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_result_dto import (
    ApplicationAccountDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.application_account_deleter import (
    ApplicationAccountDeleter,
)
from inframeld_backend.access.application.protocols.application_account_deletion_facts_reader import (
    ApplicationAccountDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.application_account_deletion_writer import (
    ApplicationAccountDeletionWriter,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.services.application_account_deletion_fingerprint_service import (
    ApplicationAccountDeletionFingerprintService,
)
from inframeld_backend.access.application.services.application_account_deletion_service import (
    ApplicationAccountDeletionService,
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
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.handlers.human_oauth_credential_error_handler import (
    register_human_oauth_credential_error_handler,
)
from inframeld_backend.access.http.responses.application_account_deletion_response import (
    ApplicationAccountDeletionResponse,
)
from inframeld_backend.access.http.routes.application_account_deletion_routes import (
    create_application_account_deletion_router,
)
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
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

ORG, PROJECT, APP = OrganizationId(UUID(int=2)), ProjectId(UUID(int=3)), PrincipalId(UUID(int=8))
HUMAN_PRINCIPAL = Principal(
    PrincipalId(UUID(int=1)), ORG, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
APPLICATION_PRINCIPAL = Principal(APP, ORG, PrincipalKind.APPLICATION, PrincipalStatus.ACTIVE)
INSTALLATION = InstallationId(UUID(int=4))
BROWSER = MockAuthenticationEvidence.browser(
    VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice")),
    installation_id=INSTALLATION,
    version=HumanCredentialVersion(1),
)
HUMAN = AccessContextDTO(HUMAN_PRINCIPAL.id, BROWSER)
APPLICATION = AccessContextDTO(APP, MockAuthenticationEvidence.application_key())
NOW = datetime(2030, 1, 1, tzinfo=UTC)
ROUTE = f"/v1/projects/{PROJECT.value}/application-accounts/{APP.value}"
URL = ROUTE + "?expectedAccessRevision=7"
KEY = "retire-Original:+/="
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": KEY,
}
CREDENTIAL = ApplicationKeyCredential(f"ifm_app_{UUID(int=10)}_" + "A" * 43)


class MockDeleter(ApplicationAccountDeleter):
    def __init__(self, *, replay: bool = False, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[
            tuple[AccessContextDTO, DeleteApplicationAccountCommand, IdempotencyContextDTO]
        ] = []
        self.result = ApplicationAccountDeletionResultDTO(
            ApplicationAccountDeletionRecordDTO(
                operation_id=OperationId("retired-original"),
                installation_id=InstallationId(UUID(int=4)),
                organization_id=ORG,
                project_id=PROJECT,
                actor_principal_id=HUMAN.actor_principal_id,
                application_principal_id=APP,
                access_revision=8,
            ),
            CompletedSynchronousOperationDTO(
                OperationId("retired-original"),
                not replay,
                OperationReplayKind.SAFE_RESULT,
                NOW + timedelta(days=1),
            ),
        )

    @override
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteApplicationAccountCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountDeletionResultDTO:
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
    deleter: ApplicationAccountDeleter,
    human: MockHumanAuthenticator | None = None,
    application: MockApplicationAuthenticator | None = None,
) -> TestClient:
    human = human or MockHumanAuthenticator()
    application = application or MockApplicationAuthenticator(APPLICATION)

    @asynccontextmanager
    async def open_deleter() -> AsyncGenerator[ApplicationAccountDeleter]:
        yield deleter

    app = FastAPI()
    register_error_handlers(app)
    register_human_oauth_credential_error_handler(app)
    app.include_router(
        create_application_account_deletion_router(
            ProductAccessDependency(
                human,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=human,
                application_authenticator=application,
            ),
            open_deleter,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("replay", [False, True])
def test_valid_delete_returns_exact_original_200(replay: bool) -> None:
    deleter = MockDeleter(replay=replay)
    with client_for(deleter) as client:
        response = client.delete(URL, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {
        "operationId": "retired-original",
        "idempotencyExpiresAt": "2030-01-02T00:00:00Z",
        "projectId": str(PROJECT.value),
        "principalId": str(APP.value),
        "accessRevision": 8,
        "accessBlocked": True,
    }
    assert response.headers["cache-control"] == "no-store" and response.headers["x-request-id"]
    assert len(deleter.calls) == 1
    access, command, context = deleter.calls[0]
    assert access == HUMAN and command == DeleteApplicationAccountCommand(PROJECT, APP, 7)
    assert context.method is HttpMethod.DELETE and context.requested_route == ROUTE
    assert context.key.value == KEY


def test_bearer_uses_actual_oauth_evidence_without_cookie_csrf() -> None:
    deleter, human = MockDeleter(), MockHumanAuthenticator()
    application = MockApplicationAuthenticator(APPLICATION)
    with client_for(deleter, human, application) as client:
        response = client.delete(
            URL, headers={"Authorization": "Bearer controlled-human", "Idempotency-Key": KEY}
        )
    assert response.status_code == 200 and len(deleter.calls) == 1
    assert deleter.calls[0][0].authentication_evidence == MockAuthenticationEvidence.human_oauth()
    assert len(human.calls) == 1 and application.calls == 0


@pytest.mark.parametrize("revision", ["0", "9007199254740991"])
def test_query_safe_integer_boundaries_reach_service_exactly(revision: str) -> None:
    deleter = MockDeleter()
    with client_for(deleter) as client:
        response = client.delete(ROUTE + "?expectedAccessRevision=" + revision, headers=HEADERS)
    assert response.status_code == 200
    assert deleter.calls[0][1].expected_access_revision == int(revision)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?expectedAccessRevision=",
        "?expectedAccessRevision=-1",
        "?expectedAccessRevision=+7",
        "?expectedAccessRevision=%2B7",
        "?expectedAccessRevision=07",
        "?expectedAccessRevision=7.0",
        "?expectedAccessRevision=7e0",
        "?expectedAccessRevision=true",
        "?expectedAccessRevision=%207",
        "?expectedAccessRevision=7%20",
        "?expectedAccessRevision=７",
        "?expectedAccessRevision=9007199254740992",
        "?expectedAccessRevision=7&expectedAccessRevision=7",
        "?expectedAccessRevision=7&unexpected=private-input",
    ],
)
def test_ambiguous_or_invalid_query_never_reaches_service(query: str) -> None:
    deleter = MockDeleter()
    with client_for(deleter) as client:
        response = client.delete(ROUTE + query, headers=HEADERS)
    assert response.status_code == 422 and deleter.calls == []
    assert response.headers["cache-control"] == "no-store" and "private-input" not in response.text


@pytest.mark.parametrize("body", [b"{}", b"null", b"x" * 32769])
def test_delete_rejects_every_body_without_service_dispatch(body: bytes) -> None:
    deleter = MockDeleter()
    with client_for(deleter) as client:
        response = client.request("DELETE", URL, content=body, headers=HEADERS)
    assert response.status_code == 422 and deleter.calls == []
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("missing", ["Cookie", "Origin", "X-Inframeld-CSRF", "Idempotency-Key"])
def test_cookie_requires_identity_origin_csrf_and_original_key(missing: str) -> None:
    deleter = MockDeleter()
    with client_for(deleter) as client:
        response = client.delete(
            URL, headers={key: value for key, value in HEADERS.items() if key != missing}
        )
    assert response.status_code == (
        401 if missing == "Cookie" else 422 if missing == "Idempotency-Key" else 403
    )
    assert deleter.calls == [] and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "headers,status",
    [
        ({**HEADERS, "Origin": "https://foreign.test"}, 403),
        ({**HEADERS, "Authorization": "Bearer controlled-human"}, 400),
        ({"Authorization": "Basic private-input", "Idempotency-Key": KEY}, 401),
        ({"Authorization": "Bearer", "Idempotency-Key": KEY}, 400),
    ],
)
def test_foreign_origin_and_invalid_or_competing_credentials_stop_dispatch(
    headers: dict[str, str],
    status: int,
) -> None:
    deleter = MockDeleter()
    with client_for(deleter) as client:
        response = client.delete(URL, headers=headers)
    assert response.status_code == status and deleter.calls == []
    assert "private-input" not in response.text and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("key", ["", "   ", "x" * 129])
def test_invalid_original_key_is_not_normalized_or_dispatched(key: str) -> None:
    deleter = MockDeleter()
    with client_for(deleter) as client:
        response = client.delete(URL, headers={**HEADERS, "Idempotency-Key": key})
    assert response.status_code == 422 and deleter.calls == []


def test_duplicate_original_keys_are_rejected() -> None:
    deleter = MockDeleter()
    headers = [(k, v) for k, v in HEADERS.items()] + [("Idempotency-Key", KEY)]
    with client_for(deleter) as client:
        response = client.delete(URL, headers=headers)
    assert response.status_code == 422 and deleter.calls == []


def test_malformed_path_is_a_safe_validation_problem() -> None:
    deleter = MockDeleter()
    with client_for(deleter) as client:
        response = client.delete(URL.replace(str(APP.value), "private-invalid-id"), headers=HEADERS)
    assert response.status_code == 422 and deleter.calls == []
    assert "private-invalid-id" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (StaleRevisionError(), 409, "stale_revision"),
        (ConflictError(), 409, "conflict"),
        (InvalidInputError(), 422, "invalid_input"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_standard_service_problems_preserve_safe_status_and_correlation(
    failure: Exception,
    status: int,
    code: str,
) -> None:
    deleter = MockDeleter(failure=failure)
    with client_for(deleter) as client:
        response = client.delete(URL, headers=HEADERS)
    assert response.status_code == status and len(deleter.calls) == 1
    assert response.json()["status"] == status and response.json()["code"] == code
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert (
        response.headers["cache-control"] == "no-store" and "retired-original" not in response.text
    )


def test_current_oauth_rejection_keeps_existing_invalid_token_challenge() -> None:
    deleter = MockDeleter(failure=HumanOAuthCredentialRejectedError())
    with client_for(deleter) as client:
        response = client.delete(
            URL, headers={"Authorization": "Bearer controlled-human", "Idempotency-Key": KEY}
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="inframeld", error="invalid_token"'
    assert response.headers["cache-control"] == "no-store"
    assert "retired-original" not in response.text and "controlled-human" not in response.text


class MockDeniedFacts(ApplicationAccountDeletionFactsReader):
    def __init__(self, events: list[str], *, application_actor: bool) -> None:
        self.events = events
        self.application_actor = application_actor

    @override
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, command: DeleteApplicationAccountCommand
    ) -> ApplicationAccountDeletionFactsDTO:
        self.events.append("facts")
        return ApplicationAccountDeletionFactsDTO(
            organization_id=ORG,
            project_id=PROJECT,
            installation_id=INSTALLATION,
            actor=ProjectActionFactsDTO(
                principal=APPLICATION_PRINCIPAL if self.application_actor else HUMAN_PRINCIPAL,
                has_pending_recovery=False,
                oauth_credential_facts=(
                    None
                    if self.application_actor
                    else HumanCredentialFactsDTO(True, BROWSER.version)
                ),
                project_status=ProjectStatus.ACTIVE,
                is_project_member=True,
                has_exact_action_grant=self.application_actor,
            ),
            application_principal=replace(APPLICATION_PRINCIPAL, status=PrincipalStatus.RETIRED),
            access_revision=42,
            checked_at=NOW,
        )

    @override
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationAccountDeletionRecordDTO | None:
        self.events.append("original")
        raise AssertionError("Current denial must precede saved-result disclosure.")


class MockForbiddenWriter(ApplicationAccountDeletionWriter):
    @override
    async def save(
        self,
        *,
        original: ApplicationAccountDeletionRecordDTO,
        expected_project_revision: int,
        checked_at: datetime,
    ) -> None:
        raise AssertionError("Current denial must precede mutation.")


@pytest.mark.parametrize("application_actor", [False, True])
def test_real_core_denies_retired_replay_or_application_before_history(
    application_actor: bool,
) -> None:
    events: list[str] = []
    operations = MockOperationIdempotency(events)
    operations.result = SAVED_RESULT
    deleter = ApplicationAccountDeletionService(
        transaction_manager=MockTransactions(events),
        deletion_facts_reader=MockDeniedFacts(events, application_actor=application_actor),
        deletion_writer=MockForbiddenWriter(),
        operation_idempotency=operations,
        deletion_fingerprint_service=ApplicationAccountDeletionFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
        ),
    )
    headers = (
        {"Authorization": "Bearer " + CREDENTIAL.value, "Idempotency-Key": KEY}
        if application_actor
        else HEADERS
    )
    with client_for(deleter) as client:
        response = client.delete(URL, headers=headers)
    assert response.status_code == 403
    assert operations.calls == 0 and events == ["begin", "facts", "rollback"]
    assert "retired-original" not in response.text and "metadata-original" not in response.text
    assert "operationId" not in response.json() and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "change",
    [
        {"access_blocked": False},
        {"idempotency_expires_at": None},
        {"access_revision": 0},
        {"access_revision": True},
        {"access_revision": 9007199254740992},
        {"cleanupOperationId": "fake"},
    ],
)
def test_response_rejects_untruthful_or_extra_completion_fields(change: dict[str, object]) -> None:
    values: dict[str, object] = {
        "operation_id": "retired-original",
        "idempotency_expires_at": NOW,
        "project_id": PROJECT.value,
        "principal_id": APP.value,
        "access_revision": 8,
        "access_blocked": True,
    }
    with pytest.raises(ValidationError):
        ApplicationAccountDeletionResponse.model_validate({**values, **change})
