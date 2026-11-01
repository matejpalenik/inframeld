"""Exercise production HTTP wiring and real PG with controlled external cookie verification."""

import asyncio
import os
from datetime import datetime, timedelta
from typing import override

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ory_kratos_client.api.frontend_api import FrontendApi
from pydantic import HttpUrl
from sqlalchemy import DateTime, Integer, String, delete, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column
from tests.support.deletion_status_scenarios import MockDeletionStatusScenarios

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap import access_composition
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
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
COOKIE = {"Cookie": "ory_kratos_session=retained-read-cookie"}
PATH = "/v1/deletions/status"
SAFE_FIELDS = {
    "outcome",
    "operationId",
    "jobState",
    "admissionConfirmed",
    "accessBlocked",
    "applicationShutdownComplete",
    "physicalCleanupComplete",
    "retentionExpiresAt",
}


class MockDeletionCookieVerifier(BrowserSessionVerifier):
    """Control only the provider result, retaining real local authentication and lookup."""

    def __init__(self, identity: VerifiedHumanIdentityDTO) -> None:
        self._identity = identity

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        if credential.value == "provider-unavailable":
            raise DependencyUnavailableError()
        return self._identity if credential.value == "retained-read-cookie" else None


def _application(
    settings: DatabaseSettings, identity: VerifiedHumanIdentityDTO, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    verifier = MockDeletionCookieVerifier(identity)

    def provider_verifier(
        api: FrontendApi, authority: IdentityAuthority, *, timeout_seconds: float
    ) -> MockDeletionCookieVerifier:
        return verifier

    monkeypatch.setattr(access_composition, "KratosBrowserSessionVerifier", provider_verifier)
    configured = get_settings().model_copy(
        update={
            "database": settings,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://unused-provider.invalid"), authority=identity.authority
            ),
            "hydra": None,
            "discovery": None,
        }
    )
    return create_app(configured)


async def test_registered_get_reads_retained_history_after_project_removal(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Private owner history qualifies safe reading, not authentic deletion or cleanup."""
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(
            session, days=7, age_days=2
        )
        owner = (await session.scalars(select(DeletionStatusObservationRow))).one()
        assert owner.expires_at is not None and owner.retention_started_at is not None
        expiry = owner.expires_at
        assert expiry - owner.retention_started_at == timedelta(days=7)
        await session.execute(delete(IdempotencyReservationRow))
        await session.execute(delete(ProjectMembershipRow))
        await session.execute(delete(ProjectRow))
    with TestClient(
        _application(temporary_postgres_settings, seed.identity, monkeypatch)
    ) as client:
        first = client.get(
            PATH, params={"operationId": seed.reservation.operation_id.value}, headers=COOKIE
        )
        assert first.status_code == 200, first.text
        assert set(first.json()) == SAFE_FIELDS
        assert first.json()["outcome"] == "retained"
        assert first.json()["operationId"] == seed.reservation.operation_id.value
        assert first.json()["physicalCleanupComplete"] is True
        assert datetime.fromisoformat(first.json()["retentionExpiresAt"]) == expiry
        assert first.headers["cache-control"] == "no-store"
        assert "location" not in first.headers
        assert (
            client.get(
                PATH, params={"operationId": seed.reservation.operation_id.value}, headers=COOKIE
            ).json()
            == first.json()
        )
    async with database.session() as session:
        assert await session.scalar(select(DeletionStatusObservationRow.expires_at)) == expiry


@pytest.mark.parametrize("state", ["binding-only", "missing", "expired", "foreign"])
async def test_registered_get_returns_only_uniform_unresolved(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    async with database.session() as session, session.begin():
        if state == "binding-only":
            seed = await MockDeletionStatusScenarios.seed_private_binding(session)
        else:
            seed = await MockDeletionStatusScenarios.seed_private_observation(
                session, age_days=31 if state == "expired" else 0
            )
        actor = seed
        if state == "foreign":
            actor = await MockDeletionStatusScenarios.seed_native_request(session)
        operation = "not-retained" if state == "missing" else seed.reservation.operation_id.value
    with TestClient(
        _application(temporary_postgres_settings, actor.identity, monkeypatch)
    ) as client:
        response = client.get(PATH, params={"operationId": operation}, headers=COOKIE)
    assert response.status_code == 200, response.text
    assert response.json() == {"outcome": "unresolved"}
    assert response.headers["cache-control"] == "no-store"
    assert "location" not in response.headers


@pytest.mark.parametrize("credential", [None, "invalid-cookie", "provider-unavailable"])
async def test_registered_get_preserves_authentication_and_dependency_failures(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
    credential: str | None,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    headers = {} if credential is None else {"Cookie": "ory_kratos_session=" + credential}
    with TestClient(
        _application(temporary_postgres_settings, seed.identity, monkeypatch),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            PATH, params={"operationId": seed.reservation.operation_id.value}, headers=headers
        )
    assert response.status_code == (503 if credential == "provider-unavailable" else 401), (
        response.text
    )
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("ineligible", ["suspended", "recovery"])
async def test_registered_get_denies_current_ineligible_initiator(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
    ineligible: str,
) -> None:
    from uuid import uuid4

    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
        if ineligible == "suspended":
            await session.execute(update(PrincipalRow).values(status=PrincipalStatus.SUSPENDED))
        else:
            session.add(
                IdentityRecoveryAdmissionRow(
                    operation_id=str(uuid4()),
                    installation_id=seed.installation_id.value,
                    authority=seed.identity.authority.value,
                    subject=seed.identity.subject.value,
                    flow_id=uuid4(),
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )
    with TestClient(
        _application(temporary_postgres_settings, seed.identity, monkeypatch),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            PATH, params={"operationId": seed.reservation.operation_id.value}, headers=COOKIE
        )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "access_denied"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "query",
    [
        "operationId=first&operationId=second",
        "operationId=known&extra=private-marker",
        "operationId=",
    ],
)
async def test_registered_get_validates_raw_query_without_echoing_private_values(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    with TestClient(
        _application(temporary_postgres_settings, seed.identity, monkeypatch)
    ) as client:
        response = client.get(PATH + "?" + query, headers=COOKIE)
    assert response.status_code == 422, response.text
    assert "private-marker" not in response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"


async def test_registered_get_keeps_malformed_history_unavailable_and_method_read_only(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
        await session.execute(
            update(DeletionStatusObservationRow).values(job_status="invalid-authoritative-state")
        )
    with TestClient(
        _application(temporary_postgres_settings, seed.identity, monkeypatch),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            PATH, params={"operationId": seed.reservation.operation_id.value}, headers=COOKIE
        )
        wrong_method = client.post(PATH, headers=COOKIE)
    assert response.status_code == 503, response.text
    assert wrong_method.status_code == 405, wrong_method.text
    assert "GET" in wrong_method.headers["allow"]
    assert response.headers["cache-control"] == wrong_method.headers["cache-control"] == "no-store"


class _ActivityBase(MappedAsDataclass, DeclarativeBase, kw_only=True):
    pass


class _ActivityRow(_ActivityBase):
    """Observe actual lock waits and transaction cleanup in this test's private database."""

    __tablename__ = "pg_stat_activity"
    __table_args__ = {"schema": "pg_catalog"}

    pid: Mapped[int] = mapped_column(Integer, primary_key=True)
    datname: Mapped[str | None] = mapped_column(String, nullable=True)
    xact_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


async def test_cancelled_registered_request_releases_lookup_transaction_and_lock_wait(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    application = _application(temporary_postgres_settings, seed.identity, monkeypatch)
    async with (
        application.router.lifespan_context(application),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application), base_url="https://api.test"
        ) as client,
    ):
        async with database.session() as blocker, blocker.begin():
            blocker_pid = (
                await blocker.execute(select(func.pg_backend_pid().cast(Integer)))
            ).scalar_one()
            await blocker.execute(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.request.organization_id.value)
                .with_for_update()
            )
            request = asyncio.create_task(
                client.get(
                    PATH,
                    params={"operationId": seed.reservation.operation_id.value},
                    headers=COOKIE,
                )
            )
            waiting_pid: int | None = None
            try:
                async with asyncio.timeout(3):
                    while waiting_pid is None:
                        if request.done():
                            response = await request
                            assert response.status_code == 200, response.text
                            pytest.fail("The HTTP read bypassed Organization coordination.")
                        async with database.session() as observer:
                            waiting_pid = await observer.scalar(
                                select(_ActivityRow.pid).where(
                                    _ActivityRow.datname == temporary_postgres_settings.name,
                                    func.pg_blocking_pids(_ActivityRow.pid)
                                    .cast(ARRAY(Integer))
                                    .contains([blocker_pid]),
                                )
                            )
                        if waiting_pid is None:
                            await asyncio.sleep(0.01)
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
            finally:
                if not request.done():
                    request.cancel()
                await asyncio.gather(request, return_exceptions=True)
        async with asyncio.timeout(2), database.session() as probe, probe.begin():
            await probe.execute(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.request.organization_id.value)
                .with_for_update()
            )
            assert (
                await probe.scalar(
                    select(_ActivityRow.xact_start).where(_ActivityRow.pid == waiting_pid)
                )
                is None
            )
