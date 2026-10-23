"""Keep recovery progress durable without losing another cleanup worker's results."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import Integer, Text, delete, func, select, update
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
from inframeld_backend.access.application.protocols.identity_recovery_repository import (
    IdentityRecoveryRepository,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_block_reader import (
    PostgresIdentityRecoveryBlockReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_identity_recovery_repository import (
    PostgresIdentityRecoveryRepository,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    ResourceNotFoundError,
)
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
    identity=VerifiedHumanIdentityDTO(authority=AUTHORITY, subject=IdentitySubject("alice")),
    event_kind=IdentityRecoveryEventKind.RECOVERY,
)
RELEASED_AT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def installation_id(database: Database) -> InstallationId:
    return await PostgresInstallationIdentityReader(database).read()


@pytest_asyncio.fixture
async def operation_id(database: Database, installation_id: InstallationId) -> OperationId:
    """Start with a real admitted recovery, including its original operation metadata."""
    async with database.session() as session, session.begin():
        service = IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session, installation_id=installation_id, authority=AUTHORITY
            )
        )
        return await service.admit(EVENT)


async def _load(
    repository: IdentityRecoveryRepository, installation_id: InstallationId
) -> IdentityRecovery:
    return await repository.get(
        installation_id=installation_id, authority=AUTHORITY, flow_id=EVENT.flow_id
    )


async def _stored(database: Database, operation_id: OperationId) -> IdentityRecoveryAdmissionRow:
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, operation_id.value)
        assert row is not None
        return row


async def _updated_rows(session: AsyncSession) -> int:
    """Count this transaction's real row updates, including a repeated save's effects."""
    count = await session.scalar(
        select(
            func.pg_stat_get_xact_tuples_updated(
                func.to_regclass("identity_recovery_admissions")
            ).cast(Integer)
        )
    )
    assert count is not None
    return count


@pytest.mark.asyncio
async def test_load_existing_recovery_without_provisioning_a_principal(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """Alice's checklist exists even if she has never joined the local application."""
    async with database.session() as session, session.begin():
        recovery = await _load(PostgresIdentityRecoveryRepository(session), installation_id)

        assert recovery.identity == (installation_id, AUTHORITY, EVENT.flow_id)
        assert recovery.subject == EVENT.identity.subject
        assert recovery.kratos_cleanup_state is IdentityRecoveryCleanupState.PENDING
        assert recovery.hydra_cleanup_state is IdentityRecoveryCleanupState.PENDING
        assert recovery.released_at is None
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 0

    assert (await _stored(database, operation_id)).operation_id == operation_id.value


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_scope", ["installation", "authority", "flow"])
async def test_load_requires_the_exact_original_scope(
    database: Database,
    installation_id: InstallationId,
    operation_id: OperationId,
    changed_scope: Literal["installation", "authority", "flow"],
) -> None:
    """The same flow value cannot retrieve an admission from another trusted scope."""
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        with pytest.raises(ResourceNotFoundError):
            await repository.get(
                installation_id=InstallationId(UUID(int=0))
                if changed_scope == "installation"
                else installation_id,
                authority=IdentityAuthority("https://other.example.test")
                if changed_scope == "authority"
                else AUTHORITY,
                flow_id=IdentityRecoveryFlowId(UUID(int=0))
                if changed_scope == "flow"
                else EVENT.flow_id,
            )

        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
            == 1
        )
    assert (await _stored(database, operation_id)).released_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["kratos", "hydra"])
@pytest.mark.parametrize(
    "outcome",
    [
        IdentityRecoveryCleanupState.CONFIRMED,
        IdentityRecoveryCleanupState.FAILED,
        IdentityRecoveryCleanupState.UNCERTAIN,
    ],
)
async def test_save_provider_progress_preserves_original_admission(
    database: Database,
    installation_id: InstallationId,
    operation_id: OperationId,
    provider: Literal["kratos", "hydra"],
    outcome: IdentityRecoveryCleanupState,
) -> None:
    """Recording one provider must preserve the other result and original event binding."""
    original = await _stored(database, operation_id)

    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        if provider == "kratos":
            recovery.record_kratos_cleanup(outcome)
        else:
            recovery.record_hydra_cleanup(outcome)
        await repository.save(recovery)

    stored = await _stored(database, operation_id)
    assert stored.operation_id == original.operation_id
    assert stored.installation_id == original.installation_id
    assert stored.authority == original.authority
    assert stored.flow_id == original.flow_id
    assert stored.subject == original.subject
    assert stored.event_kind is original.event_kind
    assert stored.admitted_at == original.admitted_at
    assert stored.released_at is None
    assert stored.kratos_cleanup_state is (
        outcome if provider == "kratos" else IdentityRecoveryCleanupState.PENDING
    )
    assert stored.hydra_cleanup_state is (
        outcome if provider == "hydra" else IdentityRecoveryCleanupState.PENDING
    )


@pytest.mark.asyncio
async def test_repeated_load_keeps_the_same_checklist_and_unsaved_progress(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        first = await _load(repository, installation_id)
        first.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)

        repeated = await _load(repository, installation_id)

        assert repeated is first
        assert repeated.kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED

    assert (await _stored(database, operation_id)).kratos_cleanup_state is (
        IdentityRecoveryCleanupState.PENDING
    )


@pytest.mark.asyncio
async def test_unchanged_save_performs_no_database_write(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """Reading and saving an unchanged checklist must not even assign a write transaction ID."""
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        transaction_id = select(func.pg_current_xact_id_if_assigned().cast(Text))
        assert await session.scalar(transaction_id) is None

        await repository.save(recovery)

        assert await session.scalar(transaction_id) is None
    assert (await _stored(database, operation_id)).released_at is None


@pytest.mark.asyncio
async def test_load_completed_password_reset_retains_release_time(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """A completed historical checklist must not restart pending cleanup when loaded."""
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow)
            .where(IdentityRecoveryAdmissionRow.operation_id == operation_id.value)
            .values(
                event_kind=IdentityRecoveryEventKind.PASSWORD_RESET,
                kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                released_at=RELEASED_AT,
            )
        )

    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)

        assert recovery.is_cleanup_confirmed
        assert recovery.is_released
        assert recovery.released_at == RELEASED_AT
        await repository.save(recovery)

    assert (await _stored(database, operation_id)).event_kind is (
        IdentityRecoveryEventKind.PASSWORD_RESET
    )


@pytest.mark.asyncio
async def test_repeated_saves_track_progress_and_skip_unchanged_results(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """After saving failure, a later confirmation uses the last successful snapshot."""
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.FAILED)
        await repository.save(recovery)
        assert await _updated_rows(session) == 1

        await repository.save(recovery)
        assert await _updated_rows(session) == 1

        recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        recovery.record_hydra_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        await repository.save(recovery)
        assert await _updated_rows(session) == 2

    stored = await _stored(database, operation_id)
    assert stored.kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    assert stored.hydra_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    assert stored.released_at is None
    assert await PostgresIdentityRecoveryBlockReader(database).is_blocked(EVENT.identity)


@pytest.mark.asyncio
async def test_save_release_preserves_its_first_timestamp_on_repeat(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """Persist domain-approved release without claiming to implement eligibility checks."""
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        recovery.record_hydra_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        recovery.release_product_block(at=RELEASED_AT)
        await repository.save(recovery)

        recovery.release_product_block(at=datetime(2026, 10, 24, tzinfo=UTC))
        await repository.save(recovery)
        assert await _updated_rows(session) == 1

    assert (await _stored(database, operation_id)).released_at == RELEASED_AT


@pytest.mark.asyncio
async def test_transaction_failure_rolls_back_saved_progress(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """A successful save is still provisional until the application commits."""
    with pytest.raises(RuntimeError, match="Simulated interruption"):
        async with database.session() as session, session.begin():
            repository = PostgresIdentityRecoveryRepository(session)
            recovery = await _load(repository, installation_id)
            recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
            await repository.save(recovery)
            raise RuntimeError("Simulated interruption before commit.")

    assert (await _stored(database, operation_id)).kratos_cleanup_state is (
        IdentityRecoveryCleanupState.PENDING
    )


@pytest.mark.asyncio
async def test_task_cancellation_rolls_back_saved_progress(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """Cancelling the application before commit must not leave partial cleanup progress."""
    saved = asyncio.Event()
    finish = asyncio.Event()

    async def worker() -> None:
        async with database.session() as session, session.begin():
            repository = PostgresIdentityRecoveryRepository(session)
            recovery = await _load(repository, installation_id)
            recovery.record_hydra_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
            await repository.save(recovery)
            saved.set()
            await finish.wait()

    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        task = tasks.create_task(worker())
        await saved.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert (await _stored(database, operation_id)).hydra_cleanup_state is (
        IdentityRecoveryCleanupState.PENDING
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["another-repository", "reconstituted"])
async def test_save_rejects_an_instance_not_loaded_here(
    database: Database,
    installation_id: InstallationId,
    operation_id: OperationId,
    source: Literal["another-repository", "reconstituted"],
) -> None:
    """Equal recovery identity does not make an untracked object safe to save."""
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        original = await _load(repository, installation_id)
        other = (
            await _load(PostgresIdentityRecoveryRepository(session), installation_id)
            if source == "another-repository"
            else IdentityRecovery(
                installation_id=installation_id,
                authority=AUTHORITY,
                flow_id=EVENT.flow_id,
                subject=EVENT.identity.subject,
            )
        )
        assert other == original
        assert other is not original
        other.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)

        with pytest.raises(RuntimeError, match="loaded"):
            await repository.save(other)
        with pytest.raises(RuntimeError, match="failed save"):
            await _load(repository, installation_id)

    assert (await _stored(database, operation_id)).kratos_cleanup_state is (
        IdentityRecoveryCleanupState.PENDING
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "save"])
async def test_repository_requires_an_active_caller_transaction(
    database: Database,
    installation_id: InstallationId,
    operation_id: OperationId,
    operation: Literal["get", "save"],
) -> None:
    async with database.session() as session:
        repository = PostgresIdentityRecoveryRepository(session)
        with pytest.raises(RuntimeError, match="active transaction"):
            if operation == "get":
                await _load(repository, installation_id)
            else:
                await repository.save(
                    IdentityRecovery(
                        installation_id=installation_id,
                        authority=AUTHORITY,
                        flow_id=EVENT.flow_id,
                        subject=EVENT.identity.subject,
                    )
                )
    assert (await _stored(database, operation_id)).released_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "save"])
async def test_repository_cannot_follow_an_aggregate_into_another_transaction(
    database: Database,
    installation_id: InstallationId,
    operation_id: OperationId,
    operation: Literal["get", "save"],
) -> None:
    async with database.session() as session:
        repository = PostgresIdentityRecoveryRepository(session)
        async with session.begin():
            recovery = await _load(repository, installation_id)

        async with session.begin():
            with pytest.raises(RuntimeError, match="another transaction"):
                if operation == "get":
                    await _load(repository, installation_id)
                else:
                    await repository.save(recovery)
    assert (await _stored(database, operation_id)).released_at is None


@pytest.mark.asyncio
async def test_concurrent_provider_updates_conflict_then_reload_without_lost_progress(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """Both workers start from pending - the loser reloads instead of erasing the winner."""
    loaded = asyncio.Barrier(2)

    async def record(provider: Literal["kratos", "hydra"]) -> bool:
        try:
            async with database.session() as session, session.begin():
                repository = PostgresIdentityRecoveryRepository(session)
                recovery = await _load(repository, installation_id)
                if provider == "kratos":
                    recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
                else:
                    recovery.record_hydra_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
                await loaded.wait()
                await repository.save(recovery)
            return True
        except ConflictError:
            return False

    async with asyncio.timeout(10):
        results = await asyncio.gather(record("kratos"), record("hydra"))
    assert sorted(results) == [False, True]
    stored = await _stored(database, operation_id)
    assert (stored.kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED) != (
        stored.hydra_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    )

    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        recovery.record_hydra_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        await repository.save(recovery)

    completed = await _stored(database, operation_id)
    assert completed.operation_id == operation_id.value
    assert completed.kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    assert completed.hydra_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    assert completed.released_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_binding", ["subject", "event-kind", "operation", "admitted-at"])
async def test_changed_original_metadata_prevents_a_stale_save(
    database: Database,
    installation_id: InstallationId,
    operation_id: OperationId,
    changed_binding: Literal["subject", "event-kind", "operation", "admitted-at"],
) -> None:
    """A loaded checklist cannot write through a changed admission binding."""
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)

        statement = update(IdentityRecoveryAdmissionRow).where(
            IdentityRecoveryAdmissionRow.operation_id == operation_id.value
        )
        if changed_binding == "subject":
            statement = statement.values(subject="another-identity")
        elif changed_binding == "event-kind":
            statement = statement.values(event_kind=IdentityRecoveryEventKind.PASSWORD_RESET)
        elif changed_binding == "operation":
            statement = statement.values(operation_id="replacement-operation")
        else:
            statement = statement.values(admitted_at=RELEASED_AT)
        async with database.session() as concurrent, concurrent.begin():
            await concurrent.execute(statement)

        with pytest.raises(ConflictError):
            await repository.save(recovery)
        with pytest.raises(RuntimeError, match="failed save"):
            await _load(repository, installation_id)

    async with database.session() as session:
        row = (await session.scalars(select(IdentityRecoveryAdmissionRow))).one()
        assert row.kratos_cleanup_state is IdentityRecoveryCleanupState.PENDING
        assert row.hydra_cleanup_state is IdentityRecoveryCleanupState.PENDING
        assert row.released_at is None


@pytest.mark.asyncio
async def test_deleted_admission_is_not_recreated_by_save(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        recovery.record_hydra_cleanup(IdentityRecoveryCleanupState.CONFIRMED)

        async with database.session() as concurrent, concurrent.begin():
            await concurrent.execute(
                delete(IdentityRecoveryAdmissionRow).where(
                    IdentityRecoveryAdmissionRow.operation_id == operation_id.value
                )
            )

        with pytest.raises(ConflictError):
            await repository.save(recovery)

    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
            == 0
        )


@pytest.mark.asyncio
async def test_repeating_old_release_cannot_clear_a_new_recovery_block(
    database: Database, installation_id: InstallationId, operation_id: OperationId
) -> None:
    """A later recovery has its own obligation even when Alice's earlier flow is complete."""
    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        recovery.record_hydra_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
        recovery.release_product_block(at=RELEASED_AT)
        await repository.save(recovery)

    async with database.session() as session, session.begin():
        later = await IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session, installation_id=installation_id, authority=AUTHORITY
            )
        ).admit(replace(EVENT, flow_id=IdentityRecoveryFlowId(UUID(int=2))))

    async with database.session() as session, session.begin():
        repository = PostgresIdentityRecoveryRepository(session)
        recovery = await _load(repository, installation_id)
        recovery.release_product_block(at=datetime(2026, 10, 24, tzinfo=UTC))
        await repository.save(recovery)

    assert (await _stored(database, operation_id)).released_at == RELEASED_AT
    assert (await _stored(database, later)).released_at is None
    assert await PostgresIdentityRecoveryBlockReader(database).is_blocked(EVENT.identity)
