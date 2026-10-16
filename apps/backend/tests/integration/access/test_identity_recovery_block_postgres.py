"""Verify current recovery blocks before wiring them into authentication."""

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, update
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
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_block_reader import (
    PostgresIdentityRecoveryBlockReader,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)

IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"),
    subject=IdentitySubject("20000000-0000-0000-0000-000000000001"),
)


def _event() -> IdentityRecoveryEventDTO:
    return IdentityRecoveryEventDTO(
        flow_id=IdentityRecoveryFlowId(uuid4()),
        identity=IDENTITY,
        event_kind=IdentityRecoveryEventKind.RECOVERY,
    )


async def _reserve(
    database: Database,
    session: AsyncSession,
    event: IdentityRecoveryEventDTO,
) -> OperationId:
    installation_id = await PostgresInstallationIdentityReader(database).read()
    service = IdentityRecoveryAdmissionService(
        PostgresIdentityRecoveryAdmissionWriter(
            session,
            installation_id=installation_id,
            authority=IDENTITY.authority,
        )
    )
    return await service.admit(event)


async def _admit(database: Database) -> OperationId:
    async with database.session() as session, session.begin():
        return await _reserve(database, session, _event())


async def _seed_released(database: Database, operation_id: OperationId) -> None:
    """Arrange released history without claiming that real provider cleanup ran."""
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
async def test_no_recovery_admission_means_no_block(database: Database) -> None:
    """An identity with no recovery history has no temporary recovery restriction."""
    assert await PostgresIdentityRecoveryBlockReader(database).is_blocked(IDENTITY) is False


@pytest.mark.asyncio
async def test_recovery_block_exists_without_a_local_account(database: Database) -> None:
    """Track the provider identity even before a local human account is linked."""
    await _admit(database)

    assert await PostgresHumanIdentityLinkReader(database).find_principal(IDENTITY) is None
    assert await PostgresIdentityRecoveryBlockReader(database).is_blocked(IDENTITY) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kratos_state", "hydra_state"),
    [
        (IdentityRecoveryCleanupState.PENDING, IdentityRecoveryCleanupState.PENDING),
        (IdentityRecoveryCleanupState.CONFIRMED, IdentityRecoveryCleanupState.PENDING),
        (IdentityRecoveryCleanupState.PENDING, IdentityRecoveryCleanupState.CONFIRMED),
        (IdentityRecoveryCleanupState.FAILED, IdentityRecoveryCleanupState.CONFIRMED),
        (IdentityRecoveryCleanupState.CONFIRMED, IdentityRecoveryCleanupState.UNCERTAIN),
        (IdentityRecoveryCleanupState.CONFIRMED, IdentityRecoveryCleanupState.CONFIRMED),
    ],
)
async def test_provider_states_do_not_release_the_block(
    database: Database,
    kratos_state: IdentityRecoveryCleanupState,
    hydra_state: IdentityRecoveryCleanupState,
) -> None:
    """Even two confirmed provider outcomes need an explicit guarded release."""
    operation_id = await _admit(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow)
            .where(IdentityRecoveryAdmissionRow.operation_id == operation_id.value)
            .values(kratos_cleanup_state=kratos_state, hydra_cleanup_state=hydra_state)
        )

    assert await PostgresIdentityRecoveryBlockReader(database).is_blocked(IDENTITY) is True


@pytest.mark.asyncio
async def test_reader_sees_committed_admission_and_release(database: Database) -> None:
    """Reuse one reader and observe fresh state after each committed change."""
    reader = PostgresIdentityRecoveryBlockReader(database)
    assert await reader.is_blocked(IDENTITY) is False

    operation_id = await _admit(database)
    assert await reader.is_blocked(IDENTITY) is True

    await _seed_released(database, operation_id)
    assert await reader.is_blocked(IDENTITY) is False


@pytest.mark.asyncio
async def test_released_history_does_not_hide_a_new_pending_block(database: Database) -> None:
    """An older released operation cannot make a newer recovery look complete."""
    older = await _admit(database)
    await _seed_released(database, older)
    await _admit(database)

    assert await PostgresIdentityRecoveryBlockReader(database).is_blocked(IDENTITY) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "other_identity",
    [
        replace(IDENTITY, authority=IdentityAuthority("kratos:other")),
        replace(IDENTITY, subject=IdentitySubject("another-subject")),
    ],
    ids=["different-authority", "different-subject"],
)
async def test_block_matches_the_exact_verified_identity(
    database: Database,
    other_identity: VerifiedHumanIdentityDTO,
) -> None:
    """A block must not affect another provider or another person."""
    await _admit(database)
    reader = PostgresIdentityRecoveryBlockReader(database)

    assert await reader.is_blocked(other_identity) is False
    assert await reader.is_blocked(IDENTITY) is True


@pytest.mark.asyncio
async def test_uncommitted_admission_is_not_visible(database: Database) -> None:
    """A separate request sees committed blocks rather than another transaction's work."""
    reader = PostgresIdentityRecoveryBlockReader(database)

    with pytest.raises(RuntimeError, match="Simulated rollback"):
        async with database.session() as session, session.begin():
            await _reserve(database, session, _event())
            assert await reader.is_blocked(IDENTITY) is False
            raise RuntimeError("Simulated rollback.")

    assert await reader.is_blocked(IDENTITY) is False


@pytest.mark.asyncio
async def test_missing_installation_identity_cannot_mean_unblocked(database: Database) -> None:
    """Missing authoritative metadata must fail the check instead of allowing access."""
    async with database.session() as session, session.begin():
        await session.execute(delete(InstallationIdentityRow))

    with pytest.raises(DependencyUnavailableError):
        await PostgresIdentityRecoveryBlockReader(database).is_blocked(IDENTITY)
