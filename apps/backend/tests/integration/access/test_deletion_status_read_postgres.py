"""Qualify current initiator reads using private history, not deletion producer proof."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import ARRAY, Integer, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.deletion_status_scenarios import (
    DeletionStatusSeedDTO,
    MockDeletionStatusScenarios,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.deletion_status_authorization_service import (
    DeletionStatusAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.postgres_deletion_status_facts_reader import (
    PostgresDeletionStatusFactsReader,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
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
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_deletion_status_reader import (
    PostgresDeletionStatusReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.deletion_status_retention_settings import (
    DeletionStatusRetentionSettings,
)
from inframeld_backend.shared.infrastructure.writers.postgres_deletion_status_binding_writer import (
    PostgresDeletionStatusBindingWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def _lookup(
    session: AsyncSession, seed: DeletionStatusSeedDTO, *, access: AccessContextDTO | None = None
) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO:
    return await DeletionStatusReadService(
        DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
        PostgresDeletionStatusReader(session),
    ).lookup(
        access=access or seed.access, query=GetDeletionStatusQuery(seed.reservation.operation_id)
    )


async def test_binding_only_projection_preserves_unknown_owner_facts(database: Database) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_binding(session)
    async with database.session() as session, session.begin():
        stored = await PostgresDeletionStatusReader(session).read(
            authorization=seed.authorization()
        )
        assert stored is not None
        assert stored.binding.request_id == seed.request_id
        assert stored.owner_revision is None
        assert stored.retention_started_at is None
        assert stored.expires_at is None
        assert isinstance(await _lookup(session, seed), UnresolvedOperationDTO)


@pytest.mark.parametrize(("days", "age_days"), [(90, 40), (7, 2)])
async def test_initiator_can_read_after_actual_project_membership_and_reservation_removal(
    database: Database,
    days: int,
    age_days: int,
) -> None:
    """No Project row, membership, grant or replay reservation is needed by this read."""
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(
            session, days=days, age_days=age_days
        )
    async with database.session() as session, session.begin():
        expected = (await session.scalars(select(DeletionStatusObservationRow))).one()
        expiry = expected.expires_at
        assert expiry is not None and expected.retention_started_at is not None
        assert expiry - expected.retention_started_at == timedelta(days=days)
        recorded = await session.scalar(select(DeletionStatusBindingRow.recorded_at))
        # A later installation policy must not rewrite the original capture or clock.
        repeated = await PostgresDeletionStatusBindingWriter(
            session, DeletionStatusRetentionSettings().to_profile()
        ).bind_original_request(
            reservation=seed.reservation,
            request_id=seed.request_id,
            expected_installation_id=seed.installation_id,
            expected_request=seed.request,
        )
        assert repeated.retention_days == days
        assert repeated.recorded_at == recorded
        await session.execute(delete(IdempotencyReservationRow))
        await session.execute(delete(ProjectMembershipRow))
        await session.execute(delete(ProjectRow))
    async with database.session() as session, session.begin():
        first = await _lookup(session, seed)
        second = await _lookup(session, seed)
        assert isinstance(first, RetainedDeletionStatusDTO)
        assert first == second
        assert first.physical_cleanup_complete is True
        assert first.expires_at == expiry
        assert await session.scalar(select(DeletionStatusBindingRow.recorded_at)) == recorded
        assert await session.scalar(select(DeletionStatusObservationRow.expires_at)) == expiry
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 0


async def test_failed_cleanup_keeps_unknown_completion_and_no_settlement_clock(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session, active=True)
    async with database.session() as session, session.begin():
        result = await _lookup(session, seed)
        assert isinstance(result, RetainedDeletionStatusDTO)
        assert result.job_status is JobStatus.FAILED
        assert result.physical_cleanup_complete is None
        assert result.expires_at is None


@pytest.mark.parametrize("different", ["installation", "organization", "principal", "operation"])
async def test_projection_does_not_disclose_another_exact_binding(
    database: Database, different: str
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    authorization = seed.authorization()
    if different == "installation":
        authorization = replace(authorization, installation_id=InstallationId(uuid4()))
    elif different == "organization":
        authorization = replace(authorization, organization_id=OrganizationId(uuid4()))
    elif different == "principal":
        authorization = replace(authorization, principal_id=PrincipalId(uuid4()))
    else:
        authorization = replace(authorization, operation_id=OperationId("absent-operation"))
    async with database.session() as session, session.begin():
        assert await PostgresDeletionStatusReader(session).read(authorization=authorization) is None


@pytest.mark.parametrize("unresolved", ["missing", "expired", "shorter-expired", "foreign"])
async def test_eligible_human_gets_uniform_unresolved_without_a_retained_match(
    database: Database, unresolved: str
) -> None:
    async with database.session() as session, session.begin():
        days = 7 if unresolved == "shorter-expired" else 30
        age_days = days + 1 if unresolved in ("expired", "shorter-expired") else 0
        seed = await MockDeletionStatusScenarios.seed_private_observation(
            session,
            days=days,
            age_days=age_days,
        )
        access = seed.access
        if unresolved == "missing":
            seed = replace(
                seed,
                reservation=replace(seed.reservation, operation_id=OperationId("never-retained")),
            )
        elif unresolved == "foreign":
            other = await MockDeletionStatusScenarios.seed_native_request(session)
            access = other.access
    async with database.session() as session, session.begin():
        assert await _lookup(session, seed, access=access) == UnresolvedOperationDTO()


@pytest.mark.parametrize("status", [PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED])
async def test_current_human_status_denies_retained_history(
    database: Database, status: PrincipalStatus
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
        await session.execute(update(PrincipalRow).values(status=status))
    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await _lookup(session, seed)


async def test_pending_recovery_denies_original_initiator(database: Database) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
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
    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await _lookup(session, seed)


async def test_stale_oauth_generation_is_rejected_before_history(database: Database) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
        await session.execute(update(HumanCredentialVersionRow).values(version=2))
    async with database.session() as session, session.begin():
        with pytest.raises(HumanOAuthCredentialRejectedError):
            await _lookup(session, seed, access=seed.oauth_access())


async def test_principal_removal_cannot_cascade_retained_history_or_authorize_read(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    async with database.session() as session, session.begin():
        await session.execute(delete(IdempotencyReservationRow))
        await session.execute(delete(ProjectMembershipRow))
        await session.execute(delete(HumanIdentityLinkRow))
        await session.execute(delete(PrincipalRow))
        assert await session.scalar(select(func.count()).select_from(DeletionStatusBindingRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(DeletionStatusObservationRow))
            == 1
        )
    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await _lookup(session, seed)


@pytest.mark.parametrize(
    "malformed", ["unknown-job", "missing-clock", "wrong-expiry", "wrong-provenance"]
)
async def test_malformed_authoritative_observation_is_unavailable_not_unresolved(
    database: Database, malformed: str
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(
            session, active=malformed == "wrong-provenance"
        )
        statement = update(DeletionStatusObservationRow)
        if malformed == "unknown-job":
            statement = statement.values(job_status="not-a-job-state")
        elif malformed == "missing-clock":
            statement = statement.values(retention_started_at=None)
        elif malformed == "wrong-expiry":
            statement = statement.values(
                expires_at=DeletionStatusObservationRow.expires_at + timedelta(days=1)
            )
        else:
            statement = statement.values(unfinished_project_id=uuid4())
        await session.execute(statement)
    async with database.session() as session, session.begin():
        with pytest.raises(DependencyUnavailableError):
            await _lookup(session, seed)


async def test_missing_installation_metadata_is_unavailable(database: Database) -> None:
    """Fail unavailable when required metadata disappears after browser authentication."""
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(
            session, with_oauth_generation=False
        )
        # This browser-only scenario never had an OAuth grant or generation history.
        assert (
            await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow)) == 0
        )
        await session.execute(
            delete(InstallationIdentityRow).where(
                InstallationIdentityRow.installation_id == seed.installation_id.value
            )
        )
    async with database.session() as session, session.begin():
        with pytest.raises(DependencyUnavailableError):
            await _lookup(session, seed)


async def _wait_for_blocker(database: Database, pid: int, task: asyncio.Task[object]) -> None:
    async with asyncio.timeout(2):
        while True:
            assert not task.done(), "The operation did not wait for Organization coordination."
            async with database.session() as observer:
                blockers = await observer.scalar(
                    select(func.pg_blocking_pids(pid).cast(ARRAY(Integer)))
                )
            if blockers:
                return
            await asyncio.sleep(0.01)


async def test_credential_change_committing_first_is_observed_after_organization_wait(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def read_after_change() -> None:
        async with database.session() as session, session.begin():
            pid_ready.set_result(
                (await session.execute(select(func.pg_backend_pid().cast(Integer)))).scalar_one()
            )
            with pytest.raises(HumanOAuthCredentialRejectedError):
                await _lookup(session, seed, access=seed.oauth_access())

    async with database.session() as changer, changer.begin():
        await changer.execute(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == seed.request.organization_id.value)
            .with_for_update()
        )
        task = asyncio.create_task(read_after_change())
        try:
            pid = await asyncio.wait_for(pid_ready, 2)
            await _wait_for_blocker(database, pid, task)
            await changer.execute(update(HumanCredentialVersionRow).values(version=2))
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
    await asyncio.wait_for(task, 2)


class MockPausedDeletionStatusReader(DeletionStatusProjectionReader):
    """Pause only after real current authorization, retaining its caller transaction."""

    def __init__(
        self, session: AsyncSession, entered: asyncio.Event, release: asyncio.Event
    ) -> None:
        self._delegate = PostgresDeletionStatusReader(session)
        self._entered = entered
        self._release = release

    @override
    async def read(
        self, *, authorization: DeletionStatusAuthorizationDTO
    ) -> DeletionStatusObservationDTO | None:
        self._entered.set()
        await self._release.wait()
        return await self._delegate.read(authorization=authorization)


async def test_read_finishing_first_holds_credential_change_until_projection_closes(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    entered, release = asyncio.Event(), asyncio.Event()
    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def read_first() -> None:
        async with database.session() as session, session.begin():
            result = await DeletionStatusReadService(
                DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
                MockPausedDeletionStatusReader(session, entered, release),
            ).lookup(
                access=seed.oauth_access(),
                query=GetDeletionStatusQuery(seed.reservation.operation_id),
            )
            assert isinstance(result, RetainedDeletionStatusDTO)

    async def change_after_read() -> None:
        async with database.session() as session, session.begin():
            pid_ready.set_result(
                (await session.execute(select(func.pg_backend_pid().cast(Integer)))).scalar_one()
            )
            await session.execute(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.request.organization_id.value)
                .with_for_update()
            )
            await session.execute(update(HumanCredentialVersionRow).values(version=2))

    reader = asyncio.create_task(read_first())
    waiting = asyncio.create_task(entered.wait())
    changer: asyncio.Task[None] | None = None
    try:
        done, _ = await asyncio.wait(
            (reader, waiting), timeout=2, return_when=asyncio.FIRST_COMPLETED
        )
        assert done, "Current authorization did not reach projection reading."
        if reader in done:
            await reader
        assert entered.is_set()
        changer = asyncio.create_task(change_after_read())
        pid = await asyncio.wait_for(pid_ready, 2)
        await _wait_for_blocker(database, pid, changer)
        release.set()
        await asyncio.wait_for(reader, 2)
        await asyncio.wait_for(changer, 2)
    finally:
        release.set()
        tasks: list[asyncio.Task[object]] = [reader, waiting]
        if changer is not None:
            tasks.append(changer)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    async with database.session() as session, session.begin():
        with pytest.raises(HumanOAuthCredentialRejectedError):
            await _lookup(session, seed, access=seed.oauth_access())


async def test_cancelled_read_releases_organization_coordination(database: Database) -> None:
    async with database.session() as session, session.begin():
        seed = await MockDeletionStatusScenarios.seed_private_observation(session)
    entered, release = asyncio.Event(), asyncio.Event()

    async def interrupted_read() -> None:
        async with database.session() as session, session.begin():
            await DeletionStatusReadService(
                DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
                MockPausedDeletionStatusReader(session, entered, release),
            ).lookup(
                access=seed.access, query=GetDeletionStatusQuery(seed.reservation.operation_id)
            )

    reader = asyncio.create_task(interrupted_read())
    waiting = asyncio.create_task(entered.wait())
    try:
        done, _ = await asyncio.wait(
            (reader, waiting), timeout=2, return_when=asyncio.FIRST_COMPLETED
        )
        assert done
        if reader in done:
            await reader
        assert entered.is_set()
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        async with asyncio.timeout(2), database.session() as changer, changer.begin():
            await changer.execute(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.request.organization_id.value)
                .with_for_update()
            )
            await changer.execute(update(HumanCredentialVersionRow).values(version=2))
    finally:
        for task in (reader, waiting):
            if not task.done():
                task.cancel()
        await asyncio.gather(reader, waiting, return_exceptions=True)
