"""Give competing identity changes turns without implementing invitation activation."""

import asyncio
import os
from dataclasses import replace
from typing import Literal
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import Integer, String, column, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_completion_facts_dto import (
    IdentityRecoveryCompletionFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_completion_facts_reader import (
    PostgresIdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
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
IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))
EVENT = IdentityRecoveryEventDTO(
    IdentityRecoveryFlowId(UUID(int=1)), IDENTITY, IdentityRecoveryEventKind.RECOVERY
)
Participant = Literal["admission", "completion", "initialization"]
_PID = column("pid", Integer)
_DATABASE = column("datname", String)
_ACTIVITY = table("pg_stat_activity", _PID, _DATABASE)


async def _acquire(session: AsyncSession, installation: InstallationId) -> None:
    await PostgresIdentityCoordinator(session).acquire(
        installation_id=installation, identity=IDENTITY
    )


async def _reserve(
    session: AsyncSession, installation: InstallationId, event: IdentityRecoveryEventDTO = EVENT
) -> IdentityRecoveryAdmissionDTO:
    return await PostgresIdentityRecoveryAdmissionWriter(
        session, installation_id=installation, authority=IDENTITY.authority
    ).reserve(event)


async def _operation(
    database: Database, installation: InstallationId, participant: Participant
) -> HumanCredentialStateDTO | IdentityRecoveryAdmissionDTO | IdentityRecoveryCompletionFactsDTO:
    if participant == "initialization":
        return await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    async with database.session() as session, session.begin():
        if participant == "admission":
            return await _reserve(session, installation)
        return await PostgresIdentityRecoveryCompletionFactsReader(session).read(
            installation_id=installation, authority=IDENTITY.authority, flow_id=EVENT.flow_id
        )


async def _wait_for_waiter[Result](
    database: Database, holder_pid: int | None, task: asyncio.Task[Result]
) -> None:
    """Require a real PostgreSQL wait before releasing the transaction it depends on."""
    async with asyncio.timeout(3):
        while not task.done():
            async with database.session() as observer:
                blockers = func.pg_blocking_pids(_PID, type_=ARRAY(Integer))
                statement = (
                    select(_PID)
                    .select_from(_ACTIVITY)
                    .where(
                        func.current_database(type_=String()) == _DATABASE,
                        (
                            blockers.contains([holder_pid])
                            if holder_pid is not None
                            else func.cardinality(blockers, type_=Integer) > 0
                        ),
                    )
                )
                waiter = await observer.scalar(statement)
            if waiter is not None:
                return
            await asyncio.sleep(0.01)
    task.result()
    raise AssertionError("The operation bypassed identity coordination.")


async def _pid(session: AsyncSession) -> int:
    return (await session.execute(select(func.pg_backend_pid(type_=Integer)))).scalar_one()


async def _counts(database: Database) -> tuple[int, int, int]:
    async with database.session() as session:
        return (
            (await session.execute(select(func.count()).select_from(PrincipalRow))).scalar_one(),
            (
                await session.execute(select(func.count()).select_from(HumanCredentialVersionRow))
            ).scalar_one(),
            (
                await session.execute(
                    select(func.count()).select_from(IdentityRecoveryAdmissionRow)
                )
            ).scalar_one(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback", [False, True])
async def test_identity_turn_lasts_until_the_transaction_ends(
    database: Database, rollback: bool
) -> None:
    """Returning from acquire must not let a competing operation enter Alice's turn."""
    installation = await PostgresInstallationIdentityReader(database).read()

    async def compete() -> None:
        async with database.session() as session, session.begin():
            await _acquire(session, installation)

    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks, database.session() as holder:
        async with holder.begin() as transaction:
            await _acquire(holder, installation)
            task = tasks.create_task(compete())
            await _wait_for_waiter(database, await _pid(holder), task)
            assert await _counts(database) == (0, 0, 0)
            if rollback:
                await transaction.rollback()
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize("different", ["installation", "authority", "subject", "delimiters"])
async def test_independent_identity_scopes_do_not_share_a_turn(
    database: Database, different: str
) -> None:
    """Bob and another installation must not wait for Alice's unrelated work."""
    installation = await PostgresInstallationIdentityReader(database).read()
    other_installation = (
        InstallationId(UUID(int=2)) if different == "installation" else installation
    )
    first = IDENTITY
    other = IDENTITY
    if different == "authority":
        other = replace(IDENTITY, authority=IdentityAuthority("kratos:other"))
    elif different == "subject":
        other = replace(IDENTITY, subject=IdentitySubject("bob"))
    elif different == "delimiters":
        first = VerifiedHumanIdentityDTO(IdentityAuthority("a:b"), IdentitySubject("c"))
        other = VerifiedHumanIdentityDTO(IdentityAuthority("a"), IdentitySubject("b:c"))
    async with asyncio.timeout(3), database.session() as holder, holder.begin():
        await PostgresIdentityCoordinator(holder).acquire(
            installation_id=installation, identity=first
        )
        async with database.session() as session, session.begin():
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=other_installation, identity=other
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("participant", ["admission", "completion", "initialization"])
async def test_each_participant_waits_and_reads_the_preceding_commit(
    database: Database, participant: Participant
) -> None:
    """Do not reuse the picture from before Alice's competing transaction finished."""
    installation = await PostgresInstallationIdentityReader(database).read()
    if participant == "completion":
        await _operation(database, installation, "admission")
    async with asyncio.timeout(12), asyncio.TaskGroup() as tasks, database.session() as holder:
        async with holder.begin():
            await _acquire(holder, installation)
            task = tasks.create_task(_operation(database, installation, participant))
            await _wait_for_waiter(database, await _pid(holder), task)
            if participant == "admission":
                await MockAccessScenarios.seed_linked_human(holder, IDENTITY)
            else:
                await _reserve(
                    holder,
                    installation,
                    replace(EVENT, flow_id=IdentityRecoveryFlowId(UUID(int=2))),
                )
        result = await task
    if isinstance(result, HumanCredentialStateDTO):
        assert result.version is not None and result.version.value == 2
        assert result.has_pending_recovery
    elif isinstance(result, IdentityRecoveryCompletionFactsDTO):
        assert result.has_other_pending_recovery
        assert result.admission.event == EVENT
    else:
        assert result.event == EVENT
        assert await _counts(database) == (1, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("participant", ["admission", "completion", "initialization"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_interrupted_lock_wait_leaves_no_partial_effects(
    database: Database, participant: Participant, cancel: bool
) -> None:
    """A timeout or cancellation must roll back and leave the identity turn usable."""
    installation = await PostgresInstallationIdentityReader(database).read()
    if participant == "completion":
        await _operation(database, installation, "admission")
    before = await _counts(database)
    async with asyncio.timeout(12), database.session() as holder:
        async with holder.begin():
            await _acquire(holder, installation)
            task = asyncio.create_task(_operation(database, installation, participant))
            try:
                await _wait_for_waiter(database, await _pid(holder), task)
                if cancel:
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(DependencyUnavailableError):
                        await task
                assert await _counts(database) == before
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        await _operation(database, installation, participant)


@pytest.mark.asyncio
async def test_link_creation_waits_then_observes_the_pending_recovery(database: Database) -> None:
    """Exercise the future admission boundary without claiming invitation activation."""
    installation = await PostgresInstallationIdentityReader(database).read()

    async def try_link() -> bool:
        async with database.session() as session, session.begin():
            await _acquire(session, installation)
            row = (await session.execute(HumanCredentialStateQueries.for_identity(IDENTITY))).one()
            if row[2]:
                return False
            await MockAccessScenarios.seed_linked_human(session, IDENTITY)
            return True

    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks, database.session() as holder:
        async with holder.begin():
            await _reserve(holder, installation)
            task = tasks.create_task(try_link())
            await _wait_for_waiter(database, await _pid(holder), task)
        assert not await task
    assert await _counts(database) == (0, 1, 1)


@pytest.mark.asyncio
async def test_completion_observes_an_account_linked_while_it_waits(database: Database) -> None:
    """Release eligibility must use Alice's newly committed account status."""
    installation = await PostgresInstallationIdentityReader(database).read()
    await _operation(database, installation, "admission")
    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks, database.session() as holder:
        async with holder.begin():
            await _acquire(holder, installation)
            task = tasks.create_task(_operation(database, installation, "completion"))
            await _wait_for_waiter(database, await _pid(holder), task)
            await MockAccessScenarios.seed_linked_human(
                holder, IDENTITY, status=PrincipalStatus.SUSPENDED
            )
        facts = await task
    assert isinstance(facts, IdentityRecoveryCompletionFactsDTO)
    assert facts.principal is not None and facts.principal.status is PrincipalStatus.SUSPENDED
    assert (await PostgresHumanCredentialStateReader(database).read(IDENTITY)).has_pending_recovery


@pytest.mark.asyncio
async def test_acquiring_coordination_does_not_flush_pending_records(database: Database) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session, session.begin() as transaction:
        pending = OrganizationRow(id=UUID(int=8), name="Not saved yet")
        session.add(pending)
        await _acquire(session, installation)
        assert pending in session.new
        async with database.session() as observer:
            assert await observer.scalar(select(func.count()).select_from(OrganizationRow)) == 0
        await transaction.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_initializer", [False, True])
async def test_initialization_takes_the_first_turn_before_recovery(
    database: Database, cancel_initializer: bool
) -> None:
    """Recovery waits for initialization to commit or roll back, then advances once."""
    installation = await PostgresInstallationIdentityReader(database).read()
    entered = asyncio.Event()
    release = asyncio.Event()
    acquire = PostgresIdentityCoordinator.acquire

    async def hold_first_turn(
        coordinator: PostgresIdentityCoordinator,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
    ) -> None:
        await acquire(coordinator, installation_id=installation_id, identity=identity)
        if not entered.is_set():
            entered.set()
            await release.wait()

    with patch.object(PostgresIdentityCoordinator, "acquire", new=hold_first_turn):
        async with asyncio.timeout(12), asyncio.TaskGroup() as tasks:
            initializing = tasks.create_task(
                PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
            )
            await entered.wait()
            admitting = tasks.create_task(_operation(database, installation, "admission"))
            await _wait_for_waiter(database, None, admitting)
            if cancel_initializer:
                initializing.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await initializing
            else:
                release.set()
                initial = await initializing
                assert initial.version is not None and initial.version.value == 1
                assert not initial.has_pending_recovery
            await admitting
    current = await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    assert current.version is not None and current.version.value == 2
    assert current.has_pending_recovery
    assert await _counts(database) == (0, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_database_snapshot_isolation_cannot_silently_use_this_protocol(
    database: Database, isolation: str
) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session, session.begin():
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await _acquire(session, installation)
    assert await _counts(database) == (0, 0, 0)


@pytest.mark.asyncio
async def test_completion_rejects_a_changed_original_lock_binding(database: Database) -> None:
    """Corrupted admission data cannot redirect completion to another identity's turn."""
    installation = await PostgresInstallationIdentityReader(database).read()
    await _operation(database, installation, "admission")
    async with asyncio.timeout(10), database.session() as holder:
        async with holder.begin():
            await _acquire(holder, installation)
            task = asyncio.create_task(_operation(database, installation, "completion"))
            try:
                await _wait_for_waiter(database, await _pid(holder), task)
                await holder.execute(
                    update(IdentityRecoveryAdmissionRow).values(subject="changed-by-test")
                )
            except BaseException:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
        try:
            with pytest.raises(RuntimeError, match="original identity binding"):
                await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with database.session() as session:
        row = (await session.scalars(select(IdentityRecoveryAdmissionRow))).one()
        assert row.released_at is None
        assert row.kratos_cleanup_state.value == "pending"
        assert row.hydra_cleanup_state.value == "pending"


@pytest.mark.asyncio
async def test_initialization_rechecks_installation_after_waiting(database: Database) -> None:
    """Metadata changing during a wait must not initialize state under a different key."""
    installation = await PostgresInstallationIdentityReader(database).read()
    async with asyncio.timeout(10), database.session() as holder:
        async with holder.begin():
            await _acquire(holder, installation)
            task = asyncio.create_task(_operation(database, installation, "initialization"))
            try:
                await _wait_for_waiter(database, await _pid(holder), task)
                await holder.execute(
                    update(InstallationIdentityRow).values(installation_id=UUID(int=99))
                )
            except BaseException:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
        try:
            with pytest.raises(DependencyUnavailableError):
                await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert await _counts(database) == (0, 0, 0)
