"""Verify durable recovery admission before wiring provider callbacks or authentication."""

import asyncio
import os
from dataclasses import replace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)

AUTHORITY = IdentityAuthority("https://identity.example.test")
EVENT = IdentityRecoveryEventDTO(
    flow_id=IdentityRecoveryFlowId(UUID("10000000-0000-0000-0000-000000000001")),
    identity=VerifiedHumanIdentityDTO(
        authority=AUTHORITY,
        subject=IdentitySubject("20000000-0000-0000-0000-000000000001"),
    ),
    event_kind=IdentityRecoveryEventKind.RECOVERY,
)


@pytest_asyncio.fixture
async def installation_id(database: Database) -> InstallationId:
    """Use the real installation identity created by the test database's migration."""
    return await PostgresInstallationIdentityReader(database).read()


def _service(
    session: AsyncSession, installation_id: InstallationId
) -> IdentityRecoveryAdmissionService:
    return IdentityRecoveryAdmissionService(
        PostgresIdentityRecoveryAdmissionWriter(
            session, installation_id=installation_id, authority=AUTHORITY
        )
    )


async def _admit(
    database: Database,
    installation_id: InstallationId,
    event: IdentityRecoveryEventDTO = EVENT,
) -> OperationId:
    async with database.session() as session, session.begin():
        return await _service(session, installation_id).admit(event)


async def _stored(database: Database, operation_id: OperationId) -> IdentityRecoveryAdmissionRow:
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, operation_id.value)
        assert row is not None
        return row


async def _pending(database: Database, installation_id: InstallationId) -> list[OperationId]:
    async with database.session() as session:
        values = await session.scalars(
            select(IdentityRecoveryAdmissionRow.operation_id).where(
                IdentityRecoveryAdmissionRow.installation_id == installation_id.value,
                IdentityRecoveryAdmissionRow.authority == AUTHORITY.value,
                IdentityRecoveryAdmissionRow.subject == EVENT.identity.subject.value,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
        )
        return [OperationId(value) for value in values]


async def _seed_completed(database: Database, operation_id: OperationId) -> None:
    """Set up a completed record directly without claiming real provider cleanup."""
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow)
            .where(IdentityRecoveryAdmissionRow.operation_id == operation_id.value)
            .values(
                kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                released_at=func.now(),
            )
        )


@pytest.mark.asyncio
async def test_recovery_before_local_admission_saves_a_pending_obligation(
    database: Database, installation_id: InstallationId
) -> None:
    """Track verified recovery without silently creating a local human account."""
    operation_id = await _admit(database, installation_id)
    row = await _stored(database, operation_id)

    assert row.installation_id == installation_id.value
    assert row.authority == AUTHORITY.value
    assert row.subject == EVENT.identity.subject.value
    assert row.flow_id == EVENT.flow_id.value
    assert row.event_kind is IdentityRecoveryEventKind.RECOVERY
    assert row.kratos_cleanup_state is IdentityRecoveryCleanupState.PENDING
    assert row.hydra_cleanup_state is IdentityRecoveryCleanupState.PENDING
    assert await _pending(database, installation_id) == [operation_id]
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 0


@pytest.mark.asyncio
async def test_rollback_leaves_no_admission_or_block(
    database: Database, installation_id: InstallationId
) -> None:
    """An interruption before commit must leave no partially admitted recovery."""
    with pytest.raises(RuntimeError, match="Simulated interruption"):
        async with database.session() as session, session.begin():
            await _service(session, installation_id).admit(EVENT)
            raise RuntimeError("Simulated interruption before commit.")

    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
            == 0
        )
    assert await _pending(database, installation_id) == []


@pytest.mark.asyncio
async def test_repeated_admission_recovers_the_original_operation(
    database: Database, installation_id: InstallationId
) -> None:
    """A retry in a new transaction must reuse the committed operation and block."""
    original = await _admit(database, installation_id)
    original_row = await _stored(database, original)

    repeated = await _admit(database, installation_id)

    assert repeated == original
    assert (await _stored(database, repeated)).admitted_at == original_row.admitted_at
    assert await _pending(database, installation_id) == [original]


@pytest.mark.asyncio
async def test_concurrent_callbacks_share_one_operation(
    database: Database, installation_id: InstallationId
) -> None:
    """Two deliveries arriving together must not create separate cleanup operations."""
    barrier = asyncio.Barrier(2)

    async def admit() -> OperationId:
        async with database.session() as session, session.begin():
            await barrier.wait()
            return await _service(session, installation_id).admit(EVENT)

    async with asyncio.timeout(10):
        first, second = await asyncio.gather(admit(), admit())

    assert first == second
    assert await _pending(database, installation_id) == [first]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed_event",
    [
        pytest.param(
            replace(
                EVENT,
                identity=replace(
                    EVENT.identity, subject=IdentitySubject("20000000-0000-0000-0000-000000000002")
                ),
            ),
            id="different-subject",
        ),
        pytest.param(
            replace(EVENT, event_kind=IdentityRecoveryEventKind.PASSWORD_RESET),
            id="different-kind",
        ),
        pytest.param(
            replace(
                EVENT,
                identity=replace(
                    EVENT.identity,
                    authority=IdentityAuthority("https://other-identity.example.test"),
                ),
            ),
            id="unconfigured-provider",
        ),
    ],
)
async def test_conflicting_callbacks_preserve_the_original_admission(
    database: Database,
    installation_id: InstallationId,
    changed_event: IdentityRecoveryEventDTO,
) -> None:
    """A reused flow cannot switch identity, event kind, or trusted provider."""
    original = await _admit(database, installation_id)

    with pytest.raises(ConflictError):
        await _admit(database, installation_id, changed_event)

    assert await _admit(database, installation_id) == original
    assert await _pending(database, installation_id) == [original]


@pytest.mark.asyncio
async def test_completed_admission_replay_does_not_recreate_its_block(
    database: Database, installation_id: InstallationId
) -> None:
    """A late duplicate must preserve completed cleanup instead of blocking again."""
    original = await _admit(database, installation_id)
    await _seed_completed(database, original)
    completed = await _stored(database, original)

    assert await _admit(database, installation_id) == original

    repeated = await _stored(database, original)
    assert repeated.released_at == completed.released_at
    assert repeated.kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    assert repeated.hydra_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    assert await _pending(database, installation_id) == []


@pytest.mark.asyncio
async def test_completed_flow_replay_preserves_a_newer_pending_block(
    database: Database, installation_id: InstallationId
) -> None:
    """Replaying a completed flow must leave a later recovery's obligation pending."""
    original = await _admit(database, installation_id)
    await _seed_completed(database, original)
    newer_event = replace(
        EVENT,
        flow_id=IdentityRecoveryFlowId(UUID("10000000-0000-0000-0000-000000000002")),
    )
    newer = await _admit(database, installation_id, newer_event)

    assert await _admit(database, installation_id) == original

    assert await _pending(database, installation_id) == [newer]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kratos_state", "hydra_state"),
    [
        (IdentityRecoveryCleanupState.CONFIRMED, IdentityRecoveryCleanupState.PENDING),
        (IdentityRecoveryCleanupState.PENDING, IdentityRecoveryCleanupState.CONFIRMED),
        (IdentityRecoveryCleanupState.CONFIRMED, IdentityRecoveryCleanupState.UNCERTAIN),
    ],
)
async def test_database_refuses_release_with_unconfirmed_provider_cleanup(
    database: Database,
    installation_id: InstallationId,
    kratos_state: IdentityRecoveryCleanupState,
    hydra_state: IdentityRecoveryCleanupState,
) -> None:
    """One confirmed provider cannot justify releasing the product-access block."""
    operation_id = await _admit(database, installation_id)

    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            await session.execute(
                update(IdentityRecoveryAdmissionRow)
                .where(IdentityRecoveryAdmissionRow.operation_id == operation_id.value)
                .values(
                    kratos_cleanup_state=kratos_state,
                    hydra_cleanup_state=hydra_state,
                    released_at=func.now(),
                )
            )

    assert await _pending(database, installation_id) == [operation_id]
