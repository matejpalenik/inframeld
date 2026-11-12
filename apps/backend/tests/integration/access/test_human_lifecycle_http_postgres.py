"""Exercise registered human lifecycle requests with PostgreSQL and controlled identity proof."""

import os
from datetime import datetime, timedelta
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api.identity_api import IdentityApi
from pydantic import HttpUrl
from sqlalchemy import delete, select
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    seed_membership_project,
)

from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_lifecycle_operation_result_row import (
    HumanLifecycleOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap import access_composition, application_factory
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]

HEADERS = {
    "Cookie": "ory_kratos_session=lifecycle-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "original-lifecycle",
}
RECEIPT_FIELDS = {
    "operationId",
    "idempotencyExpiresAt",
    "organizationId",
    "principalId",
    "accessRevision",
}


class MockLifecycleCookieVerifier(BrowserSessionVerifier):
    def __init__(self, identity: VerifiedHumanIdentityDTO) -> None:
        self._identity = identity

    @override
    async def verify(
        self, credential: BrowserSessionCredential, *, timeout_seconds: float | None = None
    ) -> VerifiedHumanIdentityDTO | None:
        return self._identity if credential.value == "lifecycle-cookie" else None


class MockLifecycleIdentityVerifier(HumanIdentityVerifier):
    def __init__(self, identity: VerifiedHumanIdentityDTO, *, unavailable: bool) -> None:
        self._identity = identity
        self._unavailable = unavailable

    @override
    async def verify(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        if self._unavailable:
            raise DependencyUnavailableError()
        return self._identity if identity == self._identity else None


def _application(
    settings: DatabaseSettings,
    scope: MembershipProjectSeedDTO,
    monkeypatch: pytest.MonkeyPatch,
    *,
    verifier: str = "current",
) -> FastAPI:
    actor_identity = scope.actor.binding.identity
    target = scope.bob_access.authentication_evidence
    assert isinstance(target, BrowserSessionAuthenticationDTO)

    def cookie_verifier(
        api: FrontendApi, authority: IdentityAuthority, *, timeout_seconds: float
    ) -> MockLifecycleCookieVerifier:
        return MockLifecycleCookieVerifier(actor_identity)

    def identity_verifier(
        api: IdentityApi, authority: IdentityAuthority
    ) -> MockLifecycleIdentityVerifier:
        return MockLifecycleIdentityVerifier(target.identity, unavailable=verifier == "unavailable")

    monkeypatch.setattr(access_composition, "KratosBrowserSessionVerifier", cookie_verifier)
    monkeypatch.setattr(application_factory, "KratosHumanIdentityVerifier", identity_verifier)
    configured = get_settings().model_copy(
        update={
            "database": settings,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://unused-provider.invalid"),
                authority=actor_identity.authority,
                admin_url=None if verifier == "absent" else HttpUrl("http://unused-admin.invalid"),
            ),
            "hydra": None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
            "discovery": None,
        }
    )
    return application_factory.create_app(configured)


def _route(scope: MembershipProjectSeedDTO, operation: str) -> str:
    return f"/v1/organizations/{scope.actor.organization_id.value}/humans/{scope.bob_id.value}/{operation}"


def _body(operation: str, revision: int) -> dict[str, object]:
    if operation == "suspend":
        return {"expectedAccessRevision": revision, "reason": "Incident reviewed"}
    return {"expectedAccessRevision": revision, "securityReviewReference": "incident/42"}


async def _revision(database: Database, scope: MembershipProjectSeedDTO) -> int:
    async with database.session() as session:
        org = await session.get(OrganizationRow, scope.actor.organization_id.value)
        assert org is not None
        return org.access_revision


async def _assert_no_original(
    database: Database, scope: MembershipProjectSeedDTO, operation: str
) -> None:
    action = (
        OrganizationAction.SUSPEND_USERS
        if operation == "suspend"
        else OrganizationAction.RESTORE_USERS
    )
    async with database.session() as session:
        assert not (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.requested_route == _route(scope, operation)
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(HumanLifecycleOperationResultRow.operation_id).where(
                    HumanLifecycleOperationResultRow.principal_id == scope.bob_id.value,
                    HumanLifecycleOperationResultRow.action_id == action,
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.target_id == scope.bob_id.value,
                    AccessAuditEventRow.action == action.value,
                )
            )
        ).all()


async def test_registered_suspend_replays_exact_original_and_denies_revoked_actor(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = await seed_membership_project(database)
    revision = await _revision(database, scope)
    url, body = _route(scope, "suspend"), _body("suspend", revision)
    with TestClient(_application(temporary_postgres_settings, scope, monkeypatch)) as client:
        first = client.post(url, json=body, headers=HEADERS)
        assert first.status_code == 202 and first.headers["cache-control"] == "no-store"
        receipt = first.json()
        assert set(receipt) == RECEIPT_FIELDS | {"accessBlocked", "cleanupOperationId"}
        assert receipt["accessBlocked"] is True and receipt["idempotencyExpiresAt"] is None
        assert receipt["organizationId"] == str(scope.actor.organization_id.value)
        assert receipt["principalId"] == str(scope.bob_id.value)
        assert receipt["accessRevision"] == revision + 1
        replay = client.post(url, json=body, headers=HEADERS)
        assert replay.status_code == 202 and replay.json() == receipt
        async with database.session() as session, session.begin():
            await session.execute(
                delete(OrganizationActionGrantRow).where(
                    OrganizationActionGrantRow.organization_id == scope.actor.organization_id.value,
                    OrganizationActionGrantRow.recipient_principal_id
                    == scope.actor.access.actor_principal_id.value,
                    OrganizationActionGrantRow.action == OrganizationAction.SUSPEND_USERS.value,
                )
            )
        denied = client.post(url, json=body, headers=HEADERS)
        assert denied.status_code == 403 and denied.headers["cache-control"] == "no-store"
        assert receipt["operationId"] not in denied.text
    async with database.session() as session:
        parent = (await session.scalars(select(HumanSuspensionObligationRow))).one()
        assert (
            parent.id == UUID(receipt["cleanupOperationId"])
            and parent.operation_id == receipt["operationId"]
        )
        target = await session.get(PrincipalRow, scope.bob_id.value)
        assert target is not None and target.status is PrincipalStatus.SUSPENDED
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == parent.operation_id
                )
            )
        ).one()
        assert audit.action == OrganizationAction.SUSPEND_USERS.value
    assert await _revision(database, scope) == revision + 1


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize("invalid", ["csrf", "duplicate", "utf8"])
async def test_registered_invalid_transport_leaves_no_original(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    invalid: str,
) -> None:
    scope = await seed_membership_project(database)
    revision = await _revision(database, scope)
    url = _route(scope, operation)
    with TestClient(_application(temporary_postgres_settings, scope, monkeypatch)) as client:
        if invalid == "csrf":
            headers = {name: value for name, value in HEADERS.items() if name != "X-Inframeld-CSRF"}
            response = client.post(url, json=_body(operation, revision), headers=headers)
            assert response.status_code == 403
        else:
            raw = (
                b'{"expectedAccessRevision":1,"expectedAccessRevision":2}'
                if invalid == "duplicate"
                else b'{"reason":"\xff"}'
            )
            response = client.post(
                url, content=raw, headers=HEADERS | {"Content-Type": "application/json"}
            )
            assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store"
    await _assert_no_original(database, scope, operation)
    assert await _revision(database, scope) == revision
    async with database.session() as session:
        principal = await session.get(PrincipalRow, scope.bob_id.value)
        assert principal is not None and principal.status is PrincipalStatus.ACTIVE
        assert not (await session.scalars(select(HumanSuspensionObligationRow.id))).all()


async def test_registered_restore_requires_original_cleanup_and_advances_version_once(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = await seed_membership_project(database)
    revision = await _revision(database, scope)
    target = scope.bob_access.authentication_evidence
    assert isinstance(target, BrowserSessionAuthenticationDTO)
    with TestClient(_application(temporary_postgres_settings, scope, monkeypatch)) as client:
        suspended = client.post(
            _route(scope, "suspend"), json=_body("suspend", revision), headers=HEADERS
        )
        assert suspended.status_code == 202
        cleanup_id = UUID(suspended.json()["cleanupOperationId"])
        url = _route(scope, "restore")
        headers = HEADERS | {"Idempotency-Key": "original-restore"}
        body = _body("restore", revision + 1)
        incomplete = client.post(url, json=body, headers=headers)
        assert incomplete.status_code == 409 and incomplete.headers["cache-control"] == "no-store"
        await _assert_no_original(database, scope, "restore")
        assert (
            await PostgresHumanCredentialStateReader(database).read(target.identity)
        ).version == target.version
        async with database.session() as session, session.begin():
            parent = await session.get(HumanSuspensionObligationRow, cleanup_id)
            assert parent is not None
            # Supply exact persisted confirmations for this PostgreSQL boundary test.
            parent.kratos_sessions = IdentityRecoveryCleanupState.CONFIRMED
            parent.hydra_cli_grants = IdentityRecoveryCleanupState.CONFIRMED
            parent.hydra_remembered_logins = IdentityRecoveryCleanupState.CONFIRMED
            parent.completed_at = parent.admitted_at
        restored = client.post(url, json=body, headers=headers)
        assert restored.status_code == 200 and restored.headers["cache-control"] == "no-store"
        receipt = restored.json()
        assert set(receipt) == RECEIPT_FIELDS and receipt["accessRevision"] == revision + 2
        expiry = receipt["idempotencyExpiresAt"]
        assert isinstance(expiry, str) and expiry.endswith("Z")
        assert datetime.fromisoformat(expiry).utcoffset() == timedelta(0)
        replay = client.post(url, json=body, headers=headers)
        assert replay.status_code == 200 and replay.json() == receipt
    assert await _revision(database, scope) == revision + 2
    current = (await PostgresHumanCredentialStateReader(database).read(target.identity)).version
    assert current is not None and current.value == target.version.value + 1
    async with database.session() as session:
        stored = (
            await session.scalars(
                select(HumanLifecycleOperationResultRow).where(
                    HumanLifecycleOperationResultRow.action_id == OrganizationAction.RESTORE_USERS
                )
            )
        ).one()
        principal = await session.get(PrincipalRow, scope.bob_id.value)
        assert (
            stored.operation_id == receipt["operationId"]
            and stored.cleanup_operation_id == cleanup_id
        )
        assert stored.credential_version == current.value
        assert principal is not None and principal.status is PrincipalStatus.ACTIVE


@pytest.mark.parametrize("verifier", ["absent", "unavailable"])
async def test_registered_restore_verifier_failure_does_not_disable_suspend(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
    verifier: str,
) -> None:
    scope = await seed_membership_project(database)
    revision = await _revision(database, scope)
    with TestClient(
        _application(temporary_postgres_settings, scope, monkeypatch, verifier=verifier)
    ) as client:
        url, body = _route(scope, "restore"), _body("restore", revision)
        unauthenticated = client.post(url, json=body, headers={"Idempotency-Key": "no-cookie"})
        assert unauthenticated.status_code == 401
        unavailable = client.post(url, json=body, headers=HEADERS)
        assert unavailable.status_code == 503 and unavailable.headers["cache-control"] == "no-store"
        await _assert_no_original(database, scope, "restore")
        suspended = client.post(
            _route(scope, "suspend"), json=_body("suspend", revision), headers=HEADERS
        )
        assert suspended.status_code == 202 and suspended.json()["accessRevision"] == revision + 1
    assert await _revision(database, scope) == revision + 1
