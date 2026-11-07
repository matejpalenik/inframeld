"""Exercise actual app routes with controlled authentication and current human-only policy."""

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import override
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_application_session_reader import MockApplicationSessionReader

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.operation_lookup_facts_dto import (
    OperationLookupFactsDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.operation_lookup_facts_reader import (
    OperationLookupFactsReader,
)
from inframeld_backend.access.application.services.operation_lookup_authorization_service import (
    OperationLookupAuthorizationService,
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
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.settings.application_key_authentication_settings import (
    ApplicationKeyAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.bootstrap.access_components import AccessComponents
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.application.dtos.original_operation_lookup_record_dto import (
    OriginalOperationLookupRecordDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.operation_lookup_reader import (
    OperationLookupReader,
)
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.original_operation_lookup_service import (
    OriginalOperationLookupService,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database

KEY = "ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43
METADATA = "/v1/projects/00000000-0000-0000-0000-000000000003/metadata"
ORIGIN = "https://account.test"
BODY = {
    "installationId": str(UUID(int=1)),
    "organizationId": str(UUID(int=2)),
    "projectId": str(UUID(int=3)),
    "method": "POST",
    "requestedRoute": "/v1/projects/{project_id}/grants",
    "key": "original-key",
    "expectedAuthority": {"family": "project_grant_read", "actionId": "create-access-groups"},
}


class MockHumanAuthentication(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    def __init__(self) -> None:
        self.cookie_calls = 0
        self.bearer_calls = 0

    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        if isinstance(credential, BrowserSessionCredential):
            self.cookie_calls += 1
            return AccessContextDTO(PrincipalId(UUID(int=10)), MockAuthenticationEvidence.browser())
        if isinstance(credential, HumanAccessTokenCredential):
            self.bearer_calls += 1
            return AccessContextDTO(
                PrincipalId(UUID(int=10)), MockAuthenticationEvidence.human_oauth()
            )
        raise AuthenticationRequiredError()


class MockCurrentLookupFacts(OperationLookupFactsReader):
    def __init__(self) -> None:
        self.calls = 0

    @override
    async def read(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> OperationLookupFactsDTO | None:
        self.calls += 1
        evidence = access.authentication_evidence
        return OperationLookupFactsDTO(
            installation_id=InstallationId(UUID(int=1)),
            principal=Principal(
                access.actor_principal_id,
                OrganizationId(UUID(int=2)),
                PrincipalKind.APPLICATION
                if isinstance(evidence, ApplicationKeyAuthenticationDTO)
                else PrincipalKind.HUMAN,
                PrincipalStatus.ACTIVE,
            ),
            project_status=ProjectStatus.ACTIVE,
            is_project_member=True,
            has_exact_action_grant=True,
            can_grant_action=True,
            has_pending_recovery=False,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                binding_matches_actor=True, current_version=evidence.version
            )
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else None,
        )


class MockOriginalHistory(OperationLookupReader):
    def __init__(self) -> None:
        self.calls = 0

    @override
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OriginalOperationLookupRecordDTO | None:
        self.calls += 1
        return None


@dataclass(frozen=True, slots=True)
class DispatchCase:
    client: TestClient
    application: MockApplicationAuthenticator
    human: MockHumanAuthentication
    facts: MockCurrentLookupFacts
    history: MockOriginalHistory


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch) -> Iterator[DispatchCase]:
    human = MockHumanAuthentication()
    app = MockApplicationAuthenticator(
        AccessContextDTO(PrincipalId(UUID(int=11)), MockAuthenticationEvidence.application_key())
    )
    facts = MockCurrentLookupFacts()
    history = MockOriginalHistory()

    def components(*_args: object, **_kwargs: object) -> AccessComponents:
        return AccessComponents(
            authenticator=human,
            kratos_client=None,
            access_token_authenticator=human,
            application_authenticator=app,
            mcp_application_authenticator=app,
            application_session_reader=MockApplicationSessionReader(
                CurrentApplicationSessionDTO(app.access.actor_principal_id, ProjectId(UUID(int=3)))
            ),
        )

    @asynccontextmanager
    async def lookup(_database: Database) -> AsyncGenerator[OriginalOperationLookup]:
        yield OriginalOperationLookupService(OperationLookupAuthorizationService(facts), history)

    monkeypatch.setattr(
        "inframeld_backend.bootstrap.application_factory.create_access_components", components
    )
    monkeypatch.setattr(
        "inframeld_backend.bootstrap.application_factory.open_original_operation_lookup", lookup
    )
    settings = get_settings().model_copy(
        update={"csrf": CSRFSettings(trusted_origins=(HttpUrl(ORIGIN),))}
    )
    client = TestClient(create_app(settings))
    try:
        yield DispatchCase(
            client=client, application=app, human=human, facts=facts, history=history
        )
    finally:
        client.close()


def test_supported_application_authenticates_then_human_only_lookup_denies_403(
    dispatch: DispatchCase,
) -> None:
    response = dispatch.client.post(
        "/v1/operations/lookup", json=BODY, headers={"Authorization": "Bearer " + KEY}
    )
    assert response.status_code == 403
    assert dispatch.application.calls == dispatch.facts.calls == 1
    assert dispatch.human.cookie_calls == dispatch.human.bearer_calls == dispatch.history.calls == 0


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (AuthenticationRequiredError(), 401),
        (AccessDeniedError(), 403),
        (DependencyUnavailableError(), 503),
    ],
)
def test_ordinary_metadata_selects_application_without_human_fallback(
    dispatch: DispatchCase, error: Exception, status: int
) -> None:
    dispatch.application.failure = error
    response = dispatch.client.get(METADATA, headers={"Authorization": "Bearer " + KEY})
    assert response.status_code == status and dispatch.application.calls == 1
    assert dispatch.human.cookie_calls == dispatch.human.bearer_calls == 0
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text


def test_identity_routes_reject_unsupported_families_before_any_authenticator(
    dispatch: DispatchCase,
) -> None:
    assert (
        dispatch.client.get("/v1/session", headers={"Authorization": "Bearer " + KEY}).status_code
        == 401
    )
    assert (
        dispatch.client.get(
            "/v1/application-session", headers={"Authorization": "Bearer human-token"}
        ).status_code
        == 401
    )
    assert (
        dispatch.application.calls
        == dispatch.human.cookie_calls
        == dispatch.human.bearer_calls
        == 0
    )


@pytest.mark.parametrize(
    "headers",
    [
        [("Authorization", "Bearer " + KEY), ("Cookie", "ory_kratos_session=cookie")],
        [("Authorization", "Bearer " + KEY), ("Authorization", "Bearer human-token")],
    ],
)
def test_competing_credentials_stop_all_authentication(
    dispatch: DispatchCase, headers: list[tuple[str, str]]
) -> None:
    response = dispatch.client.post("/v1/operations/lookup", json=BODY, headers=headers)
    assert response.status_code == 400
    assert (
        dispatch.application.calls
        == dispatch.human.cookie_calls
        == dispatch.human.bearer_calls
        == dispatch.facts.calls
        == dispatch.history.calls
        == 0
    )


def test_human_cookie_csrf_and_bearer_behavior_is_preserved(dispatch: DispatchCase) -> None:
    cookie = {"Cookie": "ory_kratos_session=cookie"}
    assert (
        dispatch.client.post("/v1/operations/lookup", json=BODY, headers=cookie).status_code == 403
    )
    assert dispatch.history.calls == dispatch.facts.calls == 0
    allowed = dispatch.client.post(
        "/v1/operations/lookup",
        json=BODY,
        headers=cookie | {"Origin": ORIGIN, "X-Inframeld-CSRF": "1"},
    )
    bearer = dispatch.client.post(
        "/v1/operations/lookup", json=BODY, headers={"Authorization": "Bearer human-token"}
    )
    assert allowed.status_code == bearer.status_code == 200
    assert dispatch.human.cookie_calls == 2 and dispatch.human.bearer_calls == 1
    assert dispatch.history.calls == dispatch.facts.calls == 2 and dispatch.application.calls == 0


def test_missing_trusted_profile_is_503_before_database_or_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def forbidden_session(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("Missing profile must fail before database I/O.")

    monkeypatch.setattr(Database, "session", forbidden_session)
    settings = get_settings().model_copy(
        update={
            "kratos": None,
            "hydra": None,
            "discovery": None,
            "application_key_authentication": ApplicationKeyAuthenticationSettings(),
        }
    )
    client = TestClient(create_app(settings))
    try:
        response = client.get(METADATA, headers={"Authorization": "Bearer " + KEY})
    finally:
        client.close()
    assert response.status_code == 503 and response.json()["code"] == "dependency_unavailable"
    assert calls == 0
