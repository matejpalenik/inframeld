"""Qualify correlation in real caller transactions, without deletion effects."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.deletion_status_scenarios import (
    DeletionStatusSeedDTO,
    MockDeletionStatusScenarios,
)

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_deletion_status_binding_writer import (
    PostgresDeletionStatusBindingWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def _bind(
    session: AsyncSession, seed: DeletionStatusSeedDTO, *, days: int = 30
) -> DeletionStatusBindingDTO:
    return await PostgresDeletionStatusBindingWriter(
        session, DeletionStatusRetentionProfile(days)
    ).bind_original_request(
        reservation=seed.reservation,
        request_id=seed.request_id,
        expected_installation_id=seed.installation_id,
        expected_request=seed.request,
    )


@pytest.mark.parametrize("days", [7, 30, 90])
async def test_bind_native_original_request_without_admitting_deletion(
    database: Database, days: int
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_native_request(session)
        bound = await _bind(session, seed, days=days)
        assert session.in_transaction()
        assert bound.operation_id == seed.reservation.operation_id
        assert bound.request_id == seed.request_id
        assert bound.retention_days == days
        assert bound.recorded_at.utcoffset() is not None
        assert await session.scalar(select(ProjectRow.status)) is ProjectStatus.ACTIVE
        for row in (DeletionStatusObservationRow, DurableJobRow, AccessAuditEventRow):
            assert await session.scalar(select(func.count()).select_from(row)) == 0
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DeletionStatusBindingRow)) == 1


async def test_caller_rollback_removes_native_reservation_and_binding(database: Database) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_native_request(session)
        await _bind(session, seed)
        await session.rollback()
    async with database.session() as session:
        for row in (DeletionStatusBindingRow, IdempotencyReservationRow):
            assert await session.scalar(select(func.count()).select_from(row)) == 0


@pytest.mark.parametrize("original_days", [7, 90])
async def test_replay_after_reservation_removal_preserves_original_profile_and_attribution(
    database: Database,
    original_days: int,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_native_request(session)
        original = await _bind(session, seed, days=original_days)
    async with database.session() as session, session.begin():
        await session.execute(delete(IdempotencyReservationRow))
    async with database.session() as session, session.begin():
        repeated = await _bind(session, seed, days=30)
        assert repeated == original
        assert (
            await session.scalar(select(func.count()).select_from(DeletionStatusObservationRow))
            == 0
        )


@pytest.mark.parametrize("changed", ["fingerprint", "route", "request_id", "installation"])
async def test_changed_original_meaning_or_attribution_conflicts(
    database: Database, changed: str
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_native_request(session)
        await _bind(session, seed)
    request = seed.request
    if changed == "fingerprint":
        seed = replace(seed, request=replace(request, fingerprint=b"X" * 32))
    elif changed == "route":
        seed = replace(seed, request=replace(request, requested_route="/different-original-route"))
    elif changed == "request_id":
        seed = replace(seed, request_id=RequestId(uuid4()))
    else:
        seed = replace(seed, installation_id=InstallationId(uuid4()))
    async with database.session() as session, session.begin():
        with pytest.raises(ConflictError):
            await _bind(session, seed)


@pytest.mark.parametrize("missing", [False, True])
async def test_missing_or_completed_reservation_cannot_create_binding(
    database: Database, missing: bool
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_native_request(session)
        if missing:
            await session.execute(delete(IdempotencyReservationRow))
        else:
            await PostgresOperationReservationWriter(session).mark_replayable(
                seed.reservation.operation_id, OperationReplayKind.ASYNC_JOB
            )
        with pytest.raises(ConflictError):
            await _bind(session, seed)
        assert await session.scalar(select(func.count()).select_from(DeletionStatusBindingRow)) == 0


@pytest.mark.parametrize(
    "changed",
    [
        "principal",
        "organization",
        "project",
        "method",
        "key",
        "action",
        "family",
        "missing-authority",
    ],
)
async def test_new_binding_matches_native_scope_and_original_meaning(
    database: Database, changed: str
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_native_request(session)
        request = seed.request
        if changed == "principal":
            request = replace(request, principal_id=PrincipalId(uuid4()))
        elif changed == "organization":
            request = replace(request, organization_id=OrganizationId(uuid4()))
        elif changed == "project":
            request = replace(request, project_id=ProjectId(uuid4()))
        elif changed == "method":
            request = replace(request, method="POST")
        elif changed == "key":
            request = replace(request, key=IdempotencyKey("different-key"))
        elif changed == "action":
            request = replace(
                request,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("create-sources")
                ),
            )
        elif changed == "family":
            request = replace(
                request,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ActionId("delete-project")
                ),
            )
        else:
            request = replace(request, lookup_authority=None)
        with pytest.raises(ConflictError):
            await _bind(session, replace(seed, request=request))
        assert await session.scalar(select(func.count()).select_from(DeletionStatusBindingRow)) == 0


@pytest.mark.parametrize("conflicting_attribution", [False, True])
async def test_concurrent_binding_cannot_replace_original_attribution(
    database: Database, conflicting_attribution: bool
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_native_request(session)
    other = replace(seed, request_id=RequestId(uuid4())) if conflicting_attribution else seed

    async def bind(candidate: DeletionStatusSeedDTO) -> DeletionStatusBindingDTO:
        async with database.session() as session, session.begin():
            return await _bind(session, candidate)

    async with asyncio.timeout(5):
        results = await asyncio.gather(bind(seed), bind(other), return_exceptions=True)
    successful = [result for result in results if isinstance(result, DeletionStatusBindingDTO)]
    assert len(successful) == (1 if conflicting_attribution else 2)
    if conflicting_attribution:
        assert sum(isinstance(result, ConflictError) for result in results) == 1
    else:
        assert successful[0] == successful[1]
    async with database.session() as session:
        stored = (await session.scalars(select(DeletionStatusBindingRow))).one()
        assert stored.request_id == successful[0].request_id.value
