"""Use production HTTP assembly and real admission/issuance with controlled provider proofs."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import override
from unittest.mock import patch
from uuid import UUID

import httpx2
import pytest
from pydantic import HttpUrl
from sqlalchemy import Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.access_group_scenarios import change_group, create_group
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import store_application_key
from tests.support.project_creation_scenarios import create_project, seed_project_creator
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.human_access_token_authentication_service import (
    HumanAccessTokenAuthenticationService,
)
from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
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
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.policies.application_key_lifetime_policy import (
    ApplicationKeyLifetimePolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_account_deletion_result_row import (
    ApplicationAccountDeletionResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_issuance_result_row import (
    ApplicationKeyIssuanceResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_revocation_result_row import (
    ApplicationKeyRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.application_key_authentication_settings import (
    ApplicationKeyAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.human_authentication_settings import (
    HumanAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.bootstrap.access_components import AccessComponents
from inframeld_backend.bootstrap.access_composition import create_access_components
from inframeld_backend.bootstrap.application_account_grant_composition import (
    open_application_account_grant_change,
)
from inframeld_backend.bootstrap.application_environment import ApplicationEnvironment
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.request_fingerprint_settings import (
    RequestFingerprintSettings,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
HTTP_AUDIENCE, MCP_AUDIENCE = "https://api.test", "https://mcp.test/mcp"
BEARER = {"Authorization": "Bearer controlled-human"}
COOKIE = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
}


class ControlledBrowserProof(BrowserSessionVerifier):
    def __init__(self, binding: HumanOAuthCredentialBindingDTO) -> None:
        self._binding = binding

    @override
    async def verify(
        self, credential: BrowserSessionCredential, *, timeout_seconds: float | None = None
    ) -> VerifiedHumanIdentityDTO | None:
        return self._binding.identity if credential.value == "controlled-cookie" else None


class ControlledTokenProof(HumanAccessTokenVerifier):
    def __init__(self, binding: HumanOAuthCredentialBindingDTO) -> None:
        self._binding = binding

    @override
    async def verify(
        self, credential: HumanAccessTokenCredential, *, timeout_seconds: float
    ) -> HumanOAuthCredentialBindingDTO | None:
        return self._binding if credential.value == "controlled-human" else None


class ControlledIdentityProof(HumanIdentityVerifier):
    def __init__(self, binding: HumanOAuthCredentialBindingDTO) -> None:
        self._binding = binding

    @override
    async def verify(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        return identity if identity == self._binding.identity else None


def _settings(
    postgres: DatabaseSettings,
    tmp_path: Path,
    *,
    http: str | None = HTTP_AUDIENCE,
    mcp: str | None = MCP_AUDIENCE,
) -> ApplicationSettings:
    fingerprint = tmp_path / "fingerprint.key"
    with os.fdopen(os.open(fingerprint, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as key:
        key.write(b"K" * 32)
    return get_settings().model_copy(
        update={
            "environment": ApplicationEnvironment.TEST,
            "database": postgres,
            "request_fingerprint": RequestFingerprintSettings(key_file=fingerprint),
            "kratos": None,
            "hydra": None,
            "discovery": None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
            "application_key_authentication": ApplicationKeyAuthenticationSettings(
                http_audience=http, mcp_audience=mcp
            ),
            "application_key_issuance": ApplicationKeyIssuanceSettings(
                default_lifetime_seconds=60, maximum_lifetime_seconds=120
            ),
        }
    )


@asynccontextmanager
async def _client(
    settings: ApplicationSettings,
    binding: HumanOAuthCredentialBindingDTO,
    *,
    raise_app_exceptions: bool = True,
) -> AsyncGenerator[httpx2.AsyncClient]:
    def assemble(
        kratos_settings: KratosSettings | None,
        hydra_settings: HydraSettings | None,
        database: Database,
        *,
        human_authentication_settings: HumanAuthenticationSettings,
        application_key_authentication_settings: ApplicationKeyAuthenticationSettings | None = None,
    ) -> AccessComponents:
        """Replace provider proofs only, preserving production current admission and key adapters."""
        access = create_access_components(
            kratos_settings,
            hydra_settings,
            database,
            human_authentication_settings=human_authentication_settings,
            application_key_authentication_settings=application_key_authentication_settings,
        )
        links = PostgresHumanIdentityLinkReader(database)
        browser = HumanSessionAuthenticationService(
            ControlledBrowserProof(binding),
            PostgresHumanCredentialStateReader(database),
            provider_timeout_seconds=human_authentication_settings.provider_timeout_seconds,
            total_timeout_seconds=human_authentication_settings.total_timeout_seconds,
        )
        bearer = HumanAccessTokenAuthenticationService(
            ControlledTokenProof(binding),
            ControlledIdentityProof(binding),
            links,
            credential_state_reader=PostgresHumanCredentialStateReader(database),
            provider_timeout_seconds=human_authentication_settings.provider_timeout_seconds,
            total_timeout_seconds=human_authentication_settings.total_timeout_seconds,
        )
        return replace(access, authenticator=browser, access_token_authenticator=bearer)

    with patch(
        "inframeld_backend.bootstrap.application_factory.create_access_components", assemble
    ):
        app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
            base_url=HTTP_AUDIENCE,
        ) as client,
    ):
        yield client


async def _effects(database: Database, route: str, *, keys: int, issues: int) -> None:
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == keys
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationKeyIssuanceResultRow))
            == issues
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "application_key_issued")
            )
            == issues
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.requested_route == route)
            )
            == issues
        )


def _safe(response: httpx2.Response) -> None:
    assert response.headers["cache-control"] == "no-store"
    assert UUID(response.headers["x-request-id"])


@pytest.mark.parametrize("family", ["cookie", "bearer"])
async def test_production_http_issues_once_recovers_safe_original_and_authenticates_key(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, family: str
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    body = {"allowedAdapters": ["mcp", "http"], "expectedAccessRevision": account.access_revision}
    headers = (COOKIE if family == "cookie" else BEARER) | {"Idempotency-Key": "issue-original"}
    async with _client(_settings(temporary_postgres_settings, tmp_path), creator.binding) as client:
        first = await client.post(route, json=body, headers=headers)
        assert first.status_code == 201 and first.json()["secretAvailable"] is True
        value = first.json()
        credential = ApplicationKeyCredential(value["key"])
        assert value["metadata"]["allowedAdapters"] == ["mcp", "http"]
        created = datetime.fromisoformat(value["metadata"]["createdAt"])
        expires = datetime.fromisoformat(value["metadata"]["expiresAt"])
        assert (expires - created).total_seconds() == 60
        identity = await client.get(
            "/v1/application-session", headers={"Authorization": "Bearer " + credential.value}
        )
        assert identity.status_code == 200 and identity.json() == {
            "principalId": str(account.principal_id.value),
            "projectId": str(project.project_id.value),
        }
        replay = await client.post(
            route, json=body, headers=BEARER | {"Idempotency-Key": "issue-original"}
        )
        assert replay.status_code == 201 and replay.json()["secretAvailable"] is False
        assert "key" not in replay.json() and credential.value not in replay.text
        assert replay.json()["metadata"] == value["metadata"]
        assert replay.json()["operationId"] == value["operationId"]
        metadata = await client.get(route, headers=BEARER)
        assert metadata.status_code == 200 and len(metadata.json()["items"]) == 1
        assert metadata.json()["items"][0] == value["metadata"]
        for response in (first, identity, replay, metadata):
            _safe(response)
    await _effects(database, route, keys=1, issues=1)


@pytest.mark.parametrize("missing", ["http", "mcp"])
@pytest.mark.parametrize("adapters", [["http"], ["mcp"], ["mcp", "http"]])
async def test_fresh_issuance_requires_only_its_selected_server_profiles(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    missing: str,
    adapters: list[str],
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    settings = _settings(
        temporary_postgres_settings,
        tmp_path,
        http=None if missing == "http" else HTTP_AUDIENCE,
        mcp=None if missing == "mcp" else MCP_AUDIENCE,
    )
    async with _client(settings, creator.binding) as client:
        response = await client.post(
            route,
            json={"allowedAdapters": adapters, "expectedAccessRevision": account.access_revision},
            headers=BEARER | {"Idempotency-Key": "profile-original"},
        )
    unavailable = missing in adapters
    assert response.status_code == (503 if unavailable else 201)
    if unavailable:
        assert "key" not in response.json()
    _safe(response)
    await _effects(database, route, keys=0 if unavailable else 1, issues=0 if unavailable else 1)


@pytest.mark.parametrize(
    "overflow", [False, True], ids=["configured-maximum", "timestamp-overflow"]
)
async def test_lifetime_rejection_leaves_no_credential_or_original(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    overflow: bool,
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    settings = _settings(temporary_postgres_settings, tmp_path)
    seconds = ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS if overflow else 121
    if overflow:
        settings = settings.model_copy(
            update={
                "application_key_issuance": ApplicationKeyIssuanceSettings(
                    default_lifetime_seconds=1, maximum_lifetime_seconds=seconds
                )
            }
        )
    async with _client(settings, creator.binding) as client:
        response = await client.post(
            route,
            json={
                "allowedAdapters": ["http"],
                "expectedAccessRevision": account.access_revision,
                "expiresInSeconds": seconds,
            },
            headers=BEARER | {"Idempotency-Key": "bad-lifetime"},
        )
    assert response.status_code == 422 and "key" not in response.json()
    _safe(response)
    await _effects(database, route, keys=0, issues=0)


@pytest.mark.parametrize("family", ["cookie", "bearer"])
async def test_registered_http_revoke_only_actor_recovers_safe_original_and_rejects_old_key(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    family: str,
) -> None:
    """Replace provider proofs only, using delivered admission, membership and exact Revoke grants."""
    seed = await seed_membership_project(database)
    joined = await change_membership(
        database, seed, revision=seed.project.access_revision, key="join-http-revoker"
    )
    account = (
        await create_account(
            database, seed.actor.access, seed.project.project_id, revision=joined.access_revision
        )
    ).account
    keys_route = f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    settings = _settings(temporary_postgres_settings, tmp_path)
    async with _client(settings, seed.actor.binding) as client:
        issued = await client.post(
            keys_route,
            json={
                "allowedAdapters": ["mcp", "http"],
                "expectedAccessRevision": account.access_revision,
                "expiresInSeconds": 120,
            },
            headers=BEARER | {"Idempotency-Key": "issue-http-revoke-target"},
        )
    assert issued.status_code == 201
    credential = ApplicationKeyCredential(issued.json()["key"])
    action = ActionId(ApplicationAccountAction.REVOKE_KEYS.value)
    async with open_application_account_grant_change(
        database, RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
    ) as grants:
        granted = await grants.set_grant(
            access=seed.actor.access,
            command=SetApplicationAccountActionGrantCommand(
                account.project_id,
                account.principal_id,
                seed.bob_id,
                action,
                False,
                issued.json()["accessRevision"],
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PUT,
                f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}/grants/{seed.bob_id.value}/{action.value}",
                IdempotencyKey("grant-http-revoke-only"),
            ),
        )
    identity = VerifiedHumanIdentityDTO(
        seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
    )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    binding = HumanOAuthCredentialBindingDTO(identity, state.installation_id, state.version)
    async with database.session() as session:
        assignments = (
            (
                await session.execute(
                    select(
                        ApplicationActionGrantRow.action, ApplicationActionGrantRow.can_grant
                    ).where(
                        ApplicationActionGrantRow.application_principal_id
                        == account.principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id == seed.bob_id.value,
                    )
                )
            )
            .tuples()
            .all()
        )
        assert assignments == [(ApplicationAccountAction.REVOKE_KEYS.value, False)]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(ProjectActionGrantRow.recipient_principal_id == seed.bob_id.value)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupManagerRow)
                .where(GroupManagerRow.principal_id == seed.bob_id.value)
            )
            == 0
        )

    route = keys_route + f"/{credential.key_id.value}/revoke"
    body = {"expectedAccessRevision": granted.access_revision}
    headers = (COOKIE if family == "cookie" else BEARER) | {
        "Idempotency-Key": "http-revoke-original"
    }
    async with _client(settings, binding) as client:
        if family == "cookie":
            for missing in ("Origin", "X-Inframeld-CSRF"):
                denied = await client.post(
                    route,
                    json=body,
                    headers={key: value for key, value in headers.items() if key != missing},
                )
                assert denied.status_code == 403
                _safe(denied)
            foreign_origin = await client.post(
                route, json=body, headers=headers | {"Origin": "https://foreign.test"}
            )
            assert foreign_origin.status_code == 403
            _safe(foreign_origin)
        missing_issue = await client.post(
            keys_route,
            json={"allowedAdapters": ["http"], "expectedAccessRevision": granted.access_revision},
            headers=headers | {"Idempotency-Key": "revoke-only-cannot-issue"},
        )
        assert missing_issue.status_code == 403
        _safe(missing_issue)
        application_denied = await client.post(
            route,
            json=body,
            headers={
                "Authorization": "Bearer " + credential.value,
                "Idempotency-Key": "app-cannot-revoke",
            },
        )
        assert application_denied.status_code == 403
        _safe(application_denied)
        for hidden in (
            route.replace(str(account.project_id.value), str(UUID(int=999))),
            route.replace(str(account.principal_id.value), str(UUID(int=999))),
            route.replace(str(credential.key_id.value), str(UUID(int=999))),
        ):
            absent = await client.post(hidden, json=body, headers=headers)
            assert absent.status_code == 404 and "metadata" not in absent.json()
            _safe(absent)
        identity_response = await client.get(
            "/v1/application-session", headers={"Authorization": "Bearer " + credential.value}
        )
        assert identity_response.status_code == 200
        first = await client.post(route, json=body, headers=headers)
        assert first.status_code == 200
        receipt = first.json()
        assert set(receipt) == {"operationId", "accessRevision", "idempotencyExpiresAt", "metadata"}
        assert receipt["accessRevision"] == granted.access_revision + 1
        assert receipt["metadata"] == issued.json()["metadata"] | {
            "revokedAt": receipt["metadata"]["revokedAt"]
        }
        assert receipt["metadata"]["revokedAt"] is not None
        replay = await client.post(route, json=body, headers=headers)
        assert replay.status_code == 200 and replay.json() == receipt
        noop = await client.post(
            route,
            json={"expectedAccessRevision": receipt["accessRevision"]},
            headers=headers | {"Idempotency-Key": "fresh-revoked-noop"},
        )
        assert noop.status_code == 200
        assert noop.json()["operationId"] != receipt["operationId"]
        assert noop.json()["accessRevision"] == receipt["accessRevision"]
        assert noop.json()["metadata"] == receipt["metadata"]
        old_key = await client.get(
            "/v1/application-session", headers={"Authorization": "Bearer " + credential.value}
        )
        assert old_key.status_code == 401
        assert (
            old_key.headers["www-authenticate"] == 'Bearer realm="inframeld", error="invalid_token"'
        )
        for response in (first, replay, noop, old_key):
            _safe(response)
            assert credential.value not in response.text and "key" not in response.json()
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(ApplicationKeyRevocationResultRow)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "application_key_revoked")
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.requested_route == route)
            )
            == 2
        )


@pytest.mark.parametrize("loss", ["revoke", "human-status", "credential"])
async def test_registered_http_revoke_checks_current_authority_before_original_disclosure(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    loss: str,
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    keys_route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    async with _client(_settings(temporary_postgres_settings, tmp_path), creator.binding) as client:
        issued = await client.post(
            keys_route,
            json={"allowedAdapters": ["http"], "expectedAccessRevision": account.access_revision},
            headers=BEARER | {"Idempotency-Key": "issue-current-revoke-target"},
        )
        assert issued.status_code == 201
        route = keys_route + f"/{issued.json()['metadata']['keyId']}/revoke"
        body = {"expectedAccessRevision": issued.json()["accessRevision"]}
        headers = BEARER | {"Idempotency-Key": "current-revoke-original"}
        first = await client.post(route, json=body, headers=headers)
        assert first.status_code == 200
        async with database.session() as session, session.begin():
            if loss == "revoke":
                await session.execute(
                    delete(ApplicationActionGrantRow).where(
                        ApplicationActionGrantRow.application_principal_id
                        == account.principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id
                        == creator.access.actor_principal_id.value,
                        ApplicationActionGrantRow.action
                        == ApplicationAccountAction.REVOKE_KEYS.value,
                    )
                )
            elif loss == "human-status":
                await session.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == creator.access.actor_principal_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
            else:
                await session.execute(
                    update(HumanCredentialVersionRow)
                    .where(
                        HumanCredentialVersionRow.installation_id
                        == creator.binding.installation_id.value,
                        HumanCredentialVersionRow.authority
                        == creator.binding.identity.authority.value,
                        HumanCredentialVersionRow.subject == creator.binding.identity.subject.value,
                    )
                    .values(version=creator.binding.version.value + 1)
                )
        denied = await client.post(route, json=body, headers=headers)
        assert denied.status_code == (401 if loss == "credential" else 403)
        assert denied.json()["code"] == ("http_error" if loss == "credential" else "access_denied")
        assert "metadata" not in denied.json() and issued.json()["key"] not in denied.text
        if loss == "credential":
            assert (
                denied.headers["www-authenticate"]
                == 'Bearer realm="inframeld", error="invalid_token"'
            )
        _safe(denied)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(ApplicationKeyRevocationResultRow)
            )
            == 1
        )
        original = await session.scalar(select(ApplicationKeyRevocationResultRow))
        assert original is not None
        assert original.operation_id == first.json()["operationId"]
        assert original.access_revision == first.json()["accessRevision"]
        assert original.revoked_at == datetime.fromisoformat(first.json()["metadata"]["revokedAt"])


@pytest.mark.parametrize("uncertain", [False, True])
async def test_http_commit_failure_never_returns_secret_or_authorizes_replacement(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    uncertain: bool,
) -> None:
    """Lose an application COMMIT acknowledgment separately from known rollback."""
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    body = {"allowedAdapters": ["http"], "expectedAccessRevision": account.access_revision}
    headers = BEARER | {"Idempotency-Key": "commit-original"}
    sessions: list[Session] = []
    hook = "after_commit" if uncertain else "before_commit"

    def reject_commit(_current: Session) -> None:
        raise RuntimeError("Controlled application COMMIT failure")

    def transaction(session: AsyncSession) -> SqlAlchemyTransactionManager:
        sessions.append(session.sync_session)
        event.listen(session.sync_session, hook, reject_commit)
        return SqlAlchemyTransactionManager(session)

    async with _client(
        _settings(temporary_postgres_settings, tmp_path),
        creator.binding,
        raise_app_exceptions=False,
    ) as client:
        try:
            with patch(
                "inframeld_backend.bootstrap.application_key_composition.SqlAlchemyTransactionManager",
                transaction,
            ):
                failed = await client.post(route, json=body, headers=headers)
        finally:
            for session in sessions:
                event.remove(session, hook, reject_commit)
        assert len(sessions) == 1 and failed.status_code == 500
        assert "key" not in failed.json() and "metadata" not in failed.json()
        _safe(failed)
        await _effects(database, route, keys=int(uncertain), issues=int(uncertain))
        if uncertain:
            recovered = await client.post(route, json=body, headers=headers)
            assert recovered.status_code == 201 and recovered.json()["secretAvailable"] is False
            assert "key" not in recovered.json()
            _safe(recovered)
    await _effects(database, route, keys=int(uncertain), issues=int(uncertain))


async def test_original_http_recovery_survives_missing_profiles_and_changed_lifetime_configuration(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    body = {"allowedAdapters": ["mcp", "http"], "expectedAccessRevision": account.access_revision}
    headers = BEARER | {"Idempotency-Key": "issue-original"}
    settings = _settings(temporary_postgres_settings, tmp_path)
    async with _client(settings, creator.binding) as client:
        first = await client.post(route, json=body, headers=headers)
        assert first.status_code == 201
    changed = settings.model_copy(
        update={
            "application_key_authentication": ApplicationKeyAuthenticationSettings(),
            "application_key_issuance": ApplicationKeyIssuanceSettings(
                default_lifetime_seconds=1, maximum_lifetime_seconds=1
            ),
        }
    )
    async with _client(changed, creator.binding) as client:
        replay = await client.post(route, json=body, headers=headers)
    assert replay.status_code == 201 and replay.json()["secretAvailable"] is False
    assert "key" not in replay.json() and replay.json()["metadata"] == first.json()["metadata"]
    assert replay.json()["operationId"] == first.json()["operationId"]
    _safe(replay)
    await _effects(database, route, keys=1, issues=1)


@pytest.mark.parametrize("loss", ["issue", "delegation", "group", "human-status", "credential"])
async def test_current_human_authority_is_required_before_original_http_disclosure(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, loss: str
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    headers = BEARER | {"Idempotency-Key": "issue-original"}
    revision = account.access_revision
    group_id = None
    if loss == "delegation":
        async with database.session() as session, session.begin():
            session.add(
                ProjectActionGrantRow(
                    project_id=project.project_id.value,
                    recipient_principal_id=account.principal_id.value,
                    recipient_kind=PrincipalKind.APPLICATION,
                    action=ProjectAction.INSPECT_BUDGET.value,
                    can_grant=False,
                )
            )
    if loss == "group":
        group = await create_group(database, creator.access, project.project_id, revision=revision)
        joined = await change_group(
            database,
            creator.access,
            group.group,
            account.principal_id,
            AccessGroupChangeKind.ADD_MEMBER,
            group.group.access_revision,
            "app-group-member",
        )
        revision, group_id = joined.access_revision, group.group.group_id
    body = {"allowedAdapters": ["http"], "expectedAccessRevision": revision}
    async with _client(_settings(temporary_postgres_settings, tmp_path), creator.binding) as client:
        first = await client.post(route, json=body, headers=headers)
        assert first.status_code == 201
        async with database.session() as session, session.begin():
            if loss == "issue":
                await session.execute(
                    delete(ApplicationActionGrantRow).where(
                        ApplicationActionGrantRow.application_principal_id
                        == account.principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id
                        == creator.access.actor_principal_id.value,
                        ApplicationActionGrantRow.action
                        == ApplicationAccountAction.ISSUE_KEYS.value,
                    )
                )
            elif loss == "delegation":
                await session.execute(
                    update(ProjectActionGrantRow)
                    .where(
                        ProjectActionGrantRow.project_id == project.project_id.value,
                        ProjectActionGrantRow.recipient_principal_id
                        == creator.access.actor_principal_id.value,
                        ProjectActionGrantRow.action == ProjectAction.INSPECT_BUDGET.value,
                    )
                    .values(can_grant=False)
                )
            elif loss == "group":
                assert group_id is not None
                # Observe current management loss, not a group-administration workflow.
                await session.execute(
                    delete(GroupManagerRow).where(
                        GroupManagerRow.project_id == project.project_id.value,
                        GroupManagerRow.group_id == group_id.value,
                        GroupManagerRow.principal_id == creator.access.actor_principal_id.value,
                    )
                )
            elif loss == "human-status":
                await session.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == creator.access.actor_principal_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
            else:
                await session.execute(
                    update(HumanCredentialVersionRow)
                    .where(
                        HumanCredentialVersionRow.installation_id
                        == creator.binding.installation_id.value,
                        HumanCredentialVersionRow.authority
                        == creator.binding.identity.authority.value,
                        HumanCredentialVersionRow.subject == creator.binding.identity.subject.value,
                    )
                    .values(version=creator.binding.version.value + 1)
                )
        replay = await client.post(route, json=body, headers=headers)
    assert replay.status_code == (401 if loss == "credential" else 403)
    assert (
        "key" not in replay.json()
        and "metadata" not in replay.json()
        and first.json()["key"] not in replay.text
    )
    _safe(replay)
    await _effects(database, route, keys=1, issues=1)


@pytest.mark.parametrize("change", ["adapter-order", "omitted-lifetime"])
async def test_changed_original_meaning_conflicts_without_a_replacement_key(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, change: str
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    body: dict[str, object] = {
        "allowedAdapters": ["mcp", "http"],
        "expectedAccessRevision": account.access_revision,
    }
    headers = BEARER | {"Idempotency-Key": "issue-original"}
    async with _client(_settings(temporary_postgres_settings, tmp_path), creator.binding) as client:
        first = await client.post(route, json=body, headers=headers)
        assert first.status_code == 201
        changed = (
            {**body, "allowedAdapters": ["http", "mcp"]}
            if change == "adapter-order"
            else {**body, "expiresInSeconds": 60}
        )
        conflict = await client.post(route, json=changed, headers=headers)
    assert conflict.status_code == 409 and "key" not in conflict.json()
    _safe(conflict)
    await _effects(database, route, keys=1, issues=1)


async def test_valid_application_cannot_issue_keys_and_never_becomes_a_human(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    key = await store_application_key(
        database,
        principal_id=account.principal_id,
        organization_id=account.organization_id,
        project_id=project.project_id,
    )
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    async with _client(_settings(temporary_postgres_settings, tmp_path), creator.binding) as client:
        response = await client.post(
            route,
            json={"allowedAdapters": ["http"], "expectedAccessRevision": account.access_revision},
            headers={"Authorization": "Bearer " + key.value, "Idempotency-Key": "app-cannot-issue"},
        )
    assert response.status_code == 403 and key.value not in response.text
    _safe(response)
    await _effects(database, route, keys=1, issues=0)


@pytest.mark.parametrize("loss", ["delegation", "retirement"])
async def test_waited_http_issuance_rechecks_current_state_before_any_effect(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, loss: str
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=project.project_id.value,
                recipient_principal_id=account.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ProjectAction.INSPECT_BUDGET.value,
                can_grant=False,
            )
        )
    route = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    task: asyncio.Task[httpx2.Response] | None = None
    async with _client(_settings(temporary_postgres_settings, tmp_path), creator.binding) as client:
        try:
            async with database.session() as holder, holder.begin():
                holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
                assert holder_pid is not None
                assert (
                    await holder.scalar(
                        select(ProjectRow.id)
                        .where(ProjectRow.id == project.project_id.value)
                        .with_for_update()
                    )
                    == project.project_id.value
                )
                task = asyncio.create_task(
                    client.post(
                        route,
                        json={
                            "allowedAdapters": ["http"],
                            "expectedAccessRevision": account.access_revision,
                        },
                        headers=BEARER | {"Idempotency-Key": "waited-issuance"},
                    )
                )
                blocked = None
                async with asyncio.timeout(3):
                    while not task.done():
                        async with database.session() as observer:
                            blocked = await observer.scalar(
                                select(pid)
                                .select_from(activity)
                                .where(
                                    name == func.current_database(type_=String()),
                                    func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                        [holder_pid]
                                    ),
                                )
                            )
                        if blocked is not None:
                            break
                        await asyncio.sleep(0.01)
                if blocked is None:
                    task.result()
                    pytest.fail("HTTP issuance bypassed the Project coordination turn.")
                if loss == "delegation":
                    await holder.execute(
                        update(ProjectActionGrantRow)
                        .where(
                            ProjectActionGrantRow.project_id == project.project_id.value,
                            ProjectActionGrantRow.recipient_principal_id
                            == creator.access.actor_principal_id.value,
                            ProjectActionGrantRow.action == ProjectAction.INSPECT_BUDGET.value,
                        )
                        .values(can_grant=False)
                    )
                else:
                    # Qualify the retirement fence, not the separate retirement operation.
                    await holder.execute(
                        update(PrincipalRow)
                        .where(PrincipalRow.id == account.principal_id.value)
                        .values(status=PrincipalStatus.RETIRED)
                    )
                await holder.execute(
                    update(ProjectRow)
                    .where(ProjectRow.id == project.project_id.value)
                    .values(access_revision=ProjectRow.access_revision + 1)
                )
            response = await task
            assert response.status_code == 403 and "key" not in response.json()
            _safe(response)
        finally:
            if task is not None:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                if isinstance(outcome, BaseException) and not isinstance(
                    outcome, asyncio.CancelledError
                ):
                    raise outcome
    await _effects(database, route, keys=0, issues=0)


@pytest.mark.parametrize("family", ["browser", "oauth"])
async def test_registered_http_retires_application_account_and_denies_original_after_grant_loss(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, family: str
) -> None:
    """Retire through the production route and recheck the same human's current Delete grant."""
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    route = (
        f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}"
    )
    human = COOKIE if family == "browser" else BEARER
    original_key = "retire-Original:+/="
    headers = human | {"Idempotency-Key": original_key}

    async with _client(_settings(temporary_postgres_settings, tmp_path), creator.binding) as client:
        issued = await client.post(
            route + "/keys",
            json={
                "allowedAdapters": ["http", "mcp"],
                "expectedAccessRevision": account.access_revision,
                "expiresInSeconds": 120,
            },
            headers=human | {"Idempotency-Key": "issue-retirement-http-target"},
        )
        assert issued.status_code == 201
        credential = ApplicationKeyCredential(issued.json()["key"])
        revision = issued.json()["accessRevision"]
        params = {"expectedAccessRevision": revision}
        key_headers = {"Authorization": "Bearer " + credential.value}
        session = await client.get("/v1/application-session", headers=key_headers)
        assert session.status_code == 200 and session.json() == {
            "principalId": str(account.principal_id.value),
            "projectId": str(account.project_id.value),
        }

        first = await client.delete(route, params=params, headers=headers)
        assert first.status_code == 200
        assert first.request.content == b""
        receipt = first.json()
        assert set(receipt) == {
            "operationId",
            "idempotencyExpiresAt",
            "projectId",
            "principalId",
            "accessRevision",
            "accessBlocked",
        }
        operation_id = receipt["operationId"]
        assert isinstance(operation_id, str) and 1 <= len(operation_id) <= 128
        expiry = datetime.fromisoformat(receipt["idempotencyExpiresAt"])
        assert expiry.utcoffset() is not None
        assert receipt["projectId"] == str(account.project_id.value)
        assert receipt["principalId"] == str(account.principal_id.value)
        assert type(receipt["accessRevision"]) is int and receipt["accessRevision"] == revision + 1
        assert receipt["accessBlocked"] is True

        rejected_key = await client.get("/v1/application-session", headers=key_headers)
        assert rejected_key.status_code == 401
        assert (
            rejected_key.headers["www-authenticate"]
            == 'Bearer realm="inframeld", error="invalid_token"'
        )
        denied = await client.delete(route, params=params, headers=headers)
        assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
        assert not set(receipt).intersection(denied.json())
        assert operation_id not in denied.text
        for response in (first, rejected_key, denied):
            _safe(response)
            assert credential.value not in response.text and "key" not in response.json()

    async with database.session() as session:
        result = await session.get(ApplicationAccountDeletionResultRow, operation_id)
        reservation = await session.get(IdempotencyReservationRow, operation_id)
        principal = await session.get(PrincipalRow, account.principal_id.value)
        key = await session.get(ApplicationKeyRow, credential.key_id.value)
        current = await session.get(ProjectRow, account.project_id.value)
        assert (
            result is not None
            and result.actor_principal_id == creator.access.actor_principal_id.value
        )
        assert (result.project_id, result.application_principal_id) == (
            account.project_id.value,
            account.principal_id.value,
        )
        assert (result.before_revision, result.access_revision) == (revision, revision + 1)
        assert reservation is not None and reservation.state is OperationReservationState.REPLAYABLE
        assert (reservation.method, reservation.requested_route, reservation.request_key) == (
            "DELETE",
            route,
            original_key,
        )
        assert reservation.expires_at == expiry
        assert principal is not None and principal.status is PrincipalStatus.RETIRED
        assert key is not None and key.revoked_at is not None
        assert current is not None and current.access_revision == revision + 1
        assert (
            await session.scalar(
                select(ApplicationActionGrantRow.action).where(
                    ApplicationActionGrantRow.project_id == account.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == account.principal_id.value,
                    ApplicationActionGrantRow.recipient_principal_id
                    == creator.access.actor_principal_id.value,
                    ApplicationActionGrantRow.action
                    == ApplicationAccountAction.DELETE_ACCOUNT.value,
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.project_id == account.project_id.value,
                    IdempotencyReservationRow.method == "DELETE",
                    IdempotencyReservationRow.requested_route == route,
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.project_id == account.project_id.value,
                    AccessAuditEventRow.target_id == account.principal_id.value,
                    AccessAuditEventRow.event_type == "application_account_retired",
                )
            )
            == 1
        )


async def test_registered_http_retirement_denials_leave_no_effects_or_original(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    credential = await store_application_key(
        database,
        principal_id=account.principal_id,
        organization_id=account.organization_id,
        project_id=account.project_id,
    )
    route = (
        f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}"
    )
    params = {"expectedAccessRevision": account.access_revision}
    key_headers = {"Authorization": "Bearer " + credential.value}
    binding = creator.binding

    async with _client(_settings(temporary_postgres_settings, tmp_path), binding) as client:
        assert (await client.get(route, headers=BEARER)).status_code == 200
        assert (await client.get("/v1/application-session", headers=key_headers)).status_code == 200
        missing_csrf = await client.delete(
            route,
            params=params,
            headers={
                "Cookie": COOKIE["Cookie"],
                "Origin": COOKIE["Origin"],
                "Idempotency-Key": "retire-missing-csrf",
            },
        )
        application = await client.delete(
            route, params=params, headers=key_headers | {"Idempotency-Key": "retire-as-application"}
        )
        async with database.session() as session, session.begin():
            version = await session.get(
                HumanCredentialVersionRow,
                (
                    binding.installation_id.value,
                    binding.identity.authority.value,
                    binding.identity.subject.value,
                ),
            )
            assert version is not None and version.version == binding.version.value
            version.version += 1
        stale_oauth = await client.delete(
            route, params=params, headers=BEARER | {"Idempotency-Key": "retire-stale-oauth"}
        )
        assert missing_csrf.status_code == application.status_code == 403
        assert missing_csrf.json()["code"] == application.json()["code"] == "access_denied"
        assert stale_oauth.status_code == 401
        assert (
            stale_oauth.headers["www-authenticate"]
            == 'Bearer realm="inframeld", error="invalid_token"'
        )
        for response in (missing_csrf, application, stale_oauth):
            _safe(response)
            assert not {"operationId", "idempotencyExpiresAt", "accessBlocked"}.intersection(
                response.json()
            )
            assert credential.value not in response.text and "controlled-human" not in response.text

    async with database.session() as session:
        principal = await session.get(PrincipalRow, account.principal_id.value)
        key = await session.get(ApplicationKeyRow, credential.key_id.value)
        current = await session.get(ProjectRow, account.project_id.value)
        assert principal is not None and principal.status is PrincipalStatus.ACTIVE
        assert key is not None and key.revoked_at is None
        assert current is not None and current.access_revision == account.access_revision
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.project_id == account.project_id.value,
                    IdempotencyReservationRow.method == "DELETE",
                    IdempotencyReservationRow.requested_route == route,
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ApplicationAccountDeletionResultRow)
                .where(
                    ApplicationAccountDeletionResultRow.project_id == account.project_id.value,
                    ApplicationAccountDeletionResultRow.application_principal_id
                    == account.principal_id.value,
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.project_id == account.project_id.value,
                    AccessAuditEventRow.target_id == account.principal_id.value,
                    AccessAuditEventRow.event_type == "application_account_retired",
                )
            )
            == 0
        )
