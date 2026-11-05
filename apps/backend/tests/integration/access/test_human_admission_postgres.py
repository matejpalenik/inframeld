"""Qualify local admission with PostgreSQL and explicitly controlled identity lookup."""

import asyncio
import os
from contextlib import ExitStack
from dataclasses import replace
from typing import Literal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.first_administrator_bootstrap_scenarios import MockBootstrapIdentityVerifier
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, seed_project_creator

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_admission_facts_dto import (
    HumanAdmissionFactsDTO,
)
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
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
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.postgres_human_admission_facts_reader import (
    PostgresHumanAdmissionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_admission_result_reader import (
    PostgresHumanAdmissionResultReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_admission_operation_result_row import (
    HumanAdmissionOperationResultRow,
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
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_human_admission_writer import (
    PostgresHumanAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.bootstrap.human_admission_composition import open_human_admission
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    IdempotencyKeyReusedError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
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
BOB_IDENTITY_ID = UUID(int=200)
_PID = column("pid", Integer)
_DATABASE = column("datname", String)
_ACTIVITY = table("pg_stat_activity", _PID, _DATABASE)


def _identity(seed: ProjectCreationSeedDTO) -> VerifiedHumanIdentityDTO:
    return VerifiedHumanIdentityDTO(
        seed.binding.identity.authority, IdentitySubject(str(BOB_IDENTITY_ID))
    )


async def _admit(
    database: Database,
    seed: ProjectCreationSeedDTO,
    *,
    key: str = "admit-bob",
    revision: int | None = None,
    verifier: HumanIdentityVerifier | None = None,
) -> HumanAdmissionResultDTO:
    fingerprints = HumanAdmissionFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"a" * 32))
    )
    async with open_human_admission(
        database,
        fingerprints,
        verifier or MockBootstrapIdentityVerifier(),
        seed.binding.identity.authority,
        5,
    ) as service:
        return await service.admit(
            access=seed.access,
            command=AdmitHumanCommand(
                seed.organization_id,
                BOB_IDENTITY_ID,
                seed.access_revision if revision is None else revision,
            ),
            context=IdempotencyContextDTO(
                "POST",
                f"/v1/organizations/{seed.organization_id.value}/human-admissions",
                IdempotencyKey(key),
            ),
        )


async def _assert_no_bob(database: Database, seed: ProjectCreationSeedDTO) -> None:
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert (
            await session.get(
                HumanIdentityLinkRow, (_identity(seed).authority.value, str(BOB_IDENTITY_ID))
            )
            is None
        )
        assert (
            await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    _identity(seed).authority.value,
                    str(BOB_IDENTITY_ID),
                ),
            )
            is None
        )
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )
        assert await session.scalar(select(OrganizationRow.access_revision)) == 1


async def _recover(
    session: AsyncSession,
    seed: ProjectCreationSeedDTO,
) -> OperationId:
    admission = await PostgresIdentityRecoveryAdmissionWriter(
        session,
        installation_id=seed.binding.installation_id,
        authority=seed.binding.identity.authority,
    ).reserve(
        IdentityRecoveryEventDTO(
            IdentityRecoveryFlowId(uuid4()),
            _identity(seed),
            IdentityRecoveryEventKind.RECOVERY,
        )
    )
    return admission.operation_id


async def _wait_for_waiter[Result](
    database: Database,
    holder_pid: int | None,
    task: asyncio.Task[Result],
) -> None:
    """Observe the actual PostgreSQL lock before changing the preceding turn."""
    async with asyncio.timeout(10):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(_PID)
                    .select_from(_ACTIVITY)
                    .where(
                        func.current_database(type_=String()) == _DATABASE,
                        (
                            func.pg_blocking_pids(_PID, type_=ARRAY(Integer)).contains([holder_pid])
                            if holder_pid is not None
                            else func.cardinality(
                                func.pg_blocking_pids(_PID, type_=ARRAY(Integer)), type_=Integer
                            )
                            > 0
                        ),
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)
    value = task.result()
    if isinstance(value, Exception):
        raise value
    pytest.fail("Admission bypassed the required coordination turn.")


async def _attempt(
    database: Database, seed: ProjectCreationSeedDTO
) -> HumanAdmissionResultDTO | Exception:
    try:
        return await _admit(database, seed)
    except Exception as error:
        return error


async def test_new_admission_commits_only_human_link_generation_audit_and_original_result(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    result = await _admit(database, seed)
    assert result.changed and result.access_revision == 2
    assert result.organization_id == seed.organization_id and result.identity == _identity(seed)
    async with database.session() as session:
        principal = await session.get(PrincipalRow, result.principal_id.value)
        assert principal is not None and principal.kind is PrincipalKind.HUMAN
        assert principal.status is PrincipalStatus.ACTIVE and principal.display_name
        link = await session.get(
            HumanIdentityLinkRow, (_identity(seed).authority.value, str(BOB_IDENTITY_ID))
        )
        assert (
            link is not None
            and link.principal_id == principal.id
            and link.organization_id == seed.organization_id.value
        )
        generation = await session.get(
            HumanCredentialVersionRow,
            (
                seed.binding.installation_id.value,
                _identity(seed).authority.value,
                str(BOB_IDENTITY_ID),
            ),
        )
        assert generation is not None and generation.version == 1
        parent = await session.get(IdempotencyReservationRow, result.operation.operation_id.value)
        assert parent is not None and parent.project_id is None
        assert (
            parent.state is OperationReservationState.REPLAYABLE
            and parent.replay_kind is OperationReplayKind.SAFE_RESULT
        )
        assert parent.expires_at == result.operation.expires_at
        original = await session.get(HumanAdmissionOperationResultRow, parent.operation_id)
        assert original is not None
        assert (original.installation_id, original.authority, original.subject) == (
            seed.binding.installation_id.value,
            _identity(seed).authority.value,
            str(BOB_IDENTITY_ID),
        )
        assert (
            original.actor_principal_id,
            original.principal_id,
            original.before_revision,
            original.access_revision,
            original.status_code,
            original.changed,
        ) == (seed.access.actor_principal_id.value, principal.id, 1, 2, 201, True)
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == parent.operation_id
                )
            )
        ).one()
        assert audit.actor_principal_id == seed.access.actor_principal_id.value
        assert audit.affected_principal_id == principal.id and audit.project_id is None
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 0
        assert await session.scalar(select(func.count()).select_from(ProjectMembershipRow)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OrganizationActionGrantRow)
                .where(OrganizationActionGrantRow.recipient_principal_id == principal.id)
            )
            == 0
        )


async def test_fresh_already_admitted_has_one_no_change_audit_and_no_generation_repair(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(HumanCredentialVersionRow).where(
                HumanCredentialVersionRow.subject == str(BOB_IDENTITY_ID)
            )
        )
    unchanged = await _admit(database, seed, key="already-admitted", revision=2)
    assert not unchanged.changed and unchanged.principal_id == first.principal_id
    assert (
        unchanged.access_revision == 2
        and unchanged.operation.operation_id != first.operation.operation_id
    )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
        assert await session.scalar(select(OrganizationRow.access_revision)) == 2
        assert (
            await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    _identity(seed).authority.value,
                    str(BOB_IDENTITY_ID),
                ),
            )
            is None
        )
        original = await session.get(
            HumanAdmissionOperationResultRow, unchanged.operation.operation_id.value
        )
        assert original is not None and (
            original.status_code,
            original.changed,
            original.before_revision,
            original.access_revision,
        ) == (200, False, 2, 2)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == original.operation_id)
            )
            == 1
        )
    replay = await _admit(database, seed, key="already-admitted", revision=2)
    assert replay == replace(unchanged, operation=replace(unchanged.operation, created=False))


async def test_replay_keeps_original_business_status_revision_expiry_and_does_not_repair(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(update(OrganizationRow).values(access_revision=9))
        await session.execute(
            delete(HumanCredentialVersionRow).where(
                HumanCredentialVersionRow.subject == str(BOB_IDENTITY_ID)
            )
        )
    replay = await _admit(database, seed)
    assert replay == replace(first, operation=replace(first.operation, created=False))
    async with database.session() as session:
        assert await session.scalar(select(OrganizationRow.access_revision)) == 9
        assert (
            await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    _identity(seed).authority.value,
                    str(BOB_IDENTITY_ID),
                ),
            )
            is None
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == first.operation.operation_id.value)
            )
            == 1
        )


async def test_revoked_current_alice_authority_denies_original_replay(database: Database) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(OrganizationActionGrantRow).where(
                OrganizationActionGrantRow.action == "admit-users"
            )
        )
    with pytest.raises(AccessDeniedError):
        await _admit(database, seed)
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 1
        )
        assert await session.get(PrincipalRow, first.principal_id.value) is not None


async def test_current_oauth_generation_is_read_from_postgres_before_admission(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    seed = replace(seed, access=AccessContextDTO(seed.access.actor_principal_id, seed.binding))
    async with database.session() as session, session.begin():
        await session.execute(
            update(HumanCredentialVersionRow)
            .where(HumanCredentialVersionRow.subject == seed.binding.identity.subject.value)
            .values(version=2)
        )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await _admit(database, seed)
    await _assert_no_bob(database, seed)


async def test_same_key_changed_meaning_never_replaces_the_original_result(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed)
    with pytest.raises(IdempotencyKeyReusedError):
        await _admit(database, seed, revision=2)
    assert (await _admit(database, seed)).principal_id == first.principal_id


@pytest.mark.parametrize("status", [PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED])
async def test_blocked_existing_bob_is_never_restored_by_new_key_or_replay(
    database: Database, status: PrincipalStatus
) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == first.principal_id.value)
            .values(status=status)
        )
    for key in ["admit-bob", "new-attempt"]:
        with pytest.raises(ConflictError):
            await _admit(database, seed, key=key, revision=2)
    async with database.session() as session:
        principal = await session.get(PrincipalRow, first.principal_id.value)
        assert principal is not None and principal.status is status
        assert await session.scalar(select(OrganizationRow.access_revision)) == 2


async def test_simultaneous_creators_admit_one_identity_and_preserve_original_replay(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    async with asyncio.timeout(30), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(_admit(database, seed))
        second = tasks.create_task(_admit(database, seed))
    a, b = first.result(), second.result()
    assert a.principal_id == b.principal_id and a.operation.operation_id == b.operation.operation_id
    assert sorted([a.operation.created, b.operation.created]) == [False, True]
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
        assert await session.scalar(select(OrganizationRow.access_revision)) == 2


async def test_different_concurrent_keys_leave_one_admission_and_no_partial_loser(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)

    async def compete(key: str) -> HumanAdmissionResultDTO | StaleRevisionError:
        try:
            return await _admit(database, seed, key=key)
        except StaleRevisionError as error:
            return error

    async with asyncio.timeout(30), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(compete("admit-bob-one"))
        second = tasks.create_task(compete("admit-bob-two"))
    outcomes = [first.result(), second.result()]
    assert sum(isinstance(value, HumanAdmissionResultDTO) for value in outcomes) == 1
    assert sum(isinstance(value, StaleRevisionError) for value in outcomes) == 1
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2


@pytest.mark.parametrize("phase", ["audit", "completion", "commit", "cancellation"])
async def test_failures_roll_back_account_link_generation_result_revision_and_audit(
    database: Database, phase: str
) -> None:
    seed = await seed_project_creator(database)
    failure = RuntimeError("controlled admission failure")

    def fail_audit(session: Session, _context: object, _instances: object) -> None:
        if any(
            isinstance(row, AccessAuditEventRow)
            and row.affected_principal_id != seed.access.actor_principal_id.value
            for row in session.new
        ):
            raise failure

    commits = 0

    def fail_commit(_session: Session) -> None:
        nonlocal commits
        commits += 1
        if commits == 2:
            raise failure

    original_save = PostgresHumanAdmissionWriter.save

    async def cancel_after_save(
        writer: PostgresHumanAdmissionWriter,
        *,
        facts: HumanAdmissionFactsDTO,
        principal: Principal,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        await original_save(
            writer, facts=facts, principal=principal, actor_id=actor_id, operation_id=operation_id
        )
        raise asyncio.CancelledError()

    if phase == "audit":
        event.listen(Session, "before_flush", fail_audit)
    if phase == "commit":
        event.listen(Session, "before_commit", fail_commit)
    try:
        with ExitStack() as injected:
            if phase == "completion":
                injected.enter_context(
                    patch.object(
                        PostgresOperationReservationWriter, "mark_replayable", side_effect=failure
                    )
                )
            elif phase == "cancellation":
                injected.enter_context(
                    patch.object(PostgresHumanAdmissionWriter, "save", cancel_after_save)
                )
            with pytest.raises(
                asyncio.CancelledError if phase == "cancellation" else RuntimeError
            ) as caught:
                await _admit(database, seed)
            if phase != "cancellation":
                assert caught.value is failure
    finally:
        if phase == "audit":
            event.remove(Session, "before_flush", fail_audit)
        if phase == "commit":
            event.remove(Session, "before_commit", fail_commit)
    await _assert_no_bob(database, seed)


@pytest.mark.parametrize("order", ["recovery-first", "admission-first"])
async def test_recovery_and_admission_share_the_exact_identity_turn(
    database: Database, order: str
) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed) if order == "admission-first" else None
    async with database.session() as session, session.begin():
        operation = await _recover(session, seed)
    with pytest.raises(ConflictError):
        await _admit(database, seed)
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, operation.value)
        assert row is not None and row.released_at is None
        link = await session.get(
            HumanIdentityLinkRow, (_identity(seed).authority.value, str(BOB_IDENTITY_ID))
        )
        if first is None:
            assert (
                link is None and await session.scalar(select(OrganizationRow.access_revision)) == 1
            )
        else:
            assert link is not None and link.principal_id == first.principal_id.value
            version = await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    _identity(seed).authority.value,
                    str(BOB_IDENTITY_ID),
                ),
            )
            assert version is not None and version.version == 2


async def test_admission_holds_identity_until_commit_before_concurrent_recovery(
    database: Database,
) -> None:
    """Recovery must see the committed Bob link before advancing his generation."""
    seed = await seed_project_creator(database)
    saved, release = asyncio.Event(), asyncio.Event()
    write = PostgresHumanAdmissionWriter.save

    async def hold_admission(
        writer: PostgresHumanAdmissionWriter,
        *,
        facts: HumanAdmissionFactsDTO,
        principal: Principal,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        await write(
            writer,
            facts=facts,
            principal=principal,
            actor_id=actor_id,
            operation_id=operation_id,
        )
        saved.set()
        await release.wait()

    async def recover() -> OperationId:
        async with database.session() as session, session.begin():
            return await _recover(session, seed)

    with patch.object(PostgresHumanAdmissionWriter, "save", new=hold_admission):
        async with asyncio.timeout(30), asyncio.TaskGroup() as tasks:
            admitting = tasks.create_task(_admit(database, seed))
            await saved.wait()
            recovering = tasks.create_task(recover())
            # This private database has only the held admission and this recovery.
            await _wait_for_waiter(database, None, recovering)
            release.set()
            result = await admitting
            recovery_id = await recovering

    assert result.changed and result.access_revision == 2
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
        assert await session.scalar(select(func.count()).select_from(HumanIdentityLinkRow)) == 2
        link = await session.get(
            HumanIdentityLinkRow, (_identity(seed).authority.value, str(BOB_IDENTITY_ID))
        )
        assert link is not None and link.principal_id == result.principal_id.value
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 1
        )
        original = await session.get(
            HumanAdmissionOperationResultRow, result.operation.operation_id.value
        )
        assert original is not None and original.principal_id == link.principal_id
        assert original.status_code == 201 and original.changed
        parent = await session.get(IdempotencyReservationRow, original.operation_id)
        assert parent is not None and parent.expires_at == result.operation.expires_at
        assert parent.state is OperationReservationState.REPLAYABLE
        recovery = await session.get(IdentityRecoveryAdmissionRow, recovery_id.value)
        assert recovery is not None and recovery.released_at is None
        assert recovery.subject == str(BOB_IDENTITY_ID)
        assert recovery.kratos_cleanup_state is IdentityRecoveryCleanupState.PENDING
        assert recovery.hydra_cleanup_state is IdentityRecoveryCleanupState.PENDING
        version = await session.get(
            HumanCredentialVersionRow,
            (
                seed.binding.installation_id.value,
                _identity(seed).authority.value,
                str(BOB_IDENTITY_ID),
            ),
        )
        assert version is not None and version.version == 2
        before_revision = await session.scalar(select(OrganizationRow.access_revision))

    with pytest.raises(ConflictError):
        await _admit(database, seed)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
        assert await session.scalar(select(func.count()).select_from(HumanIdentityLinkRow)) == 2
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 1
        )
        assert await session.scalar(select(OrganizationRow.access_revision)) == before_revision
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value,
                )
            )
            == 1
        )
        version = await session.get(
            HumanCredentialVersionRow,
            (
                seed.binding.installation_id.value,
                _identity(seed).authority.value,
                str(BOB_IDENTITY_ID),
            ),
        )
        recovery = await session.get(IdentityRecoveryAdmissionRow, recovery_id.value)
        assert version is not None and version.version == 2
        assert recovery is not None and recovery.released_at is None


@pytest.mark.parametrize("missing_generation", [False, True])
async def test_completed_history_is_not_a_permanent_ban_but_missing_generation_fails_closed(
    database: Database, missing_generation: bool
) -> None:
    seed = await seed_project_creator(database)
    async with database.session() as session, session.begin():
        operation = await _recover(session, seed)
        # Controlled completed history tests the local decision, not provider cleanup proof.
        await session.execute(
            update(IdentityRecoveryAdmissionRow)
            .where(IdentityRecoveryAdmissionRow.operation_id == operation.value)
            .values(
                kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                released_at=func.now(),
            )
        )
        if missing_generation:
            await session.execute(
                delete(HumanCredentialVersionRow).where(
                    HumanCredentialVersionRow.subject == str(BOB_IDENTITY_ID)
                )
            )
        else:
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(HumanCredentialVersionRow.subject == str(BOB_IDENTITY_ID))
                .values(version=8)
            )
    if missing_generation:
        with pytest.raises(DependencyUnavailableError):
            await _admit(database, seed)
    else:
        result = await _admit(database, seed)
        assert result.changed
        async with database.session() as session:
            version = await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    _identity(seed).authority.value,
                    str(BOB_IDENTITY_ID),
                ),
            )
            assert version is not None and version.version == 8


@pytest.mark.parametrize("turn", ["identity", "organization"])
async def test_waiters_reread_recovery_and_authority_after_coordination(
    database: Database, turn: Literal["identity", "organization"]
) -> None:
    seed = await seed_project_creator(database)
    async with asyncio.timeout(30), asyncio.TaskGroup() as tasks, database.session() as holder:
        async with holder.begin():
            if turn == "identity":
                await PostgresIdentityCoordinator(holder).acquire(
                    installation_id=seed.binding.installation_id, identity=_identity(seed)
                )
            else:
                await holder.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == seed.organization_id.value)
                    .with_for_update()
                )
            pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert pid is not None
            waiter = tasks.create_task(_attempt(database, seed))
            await _wait_for_waiter(database, pid, waiter)
            if turn == "identity":
                await _recover(holder, seed)
            else:
                await holder.execute(
                    delete(OrganizationActionGrantRow).where(
                        OrganizationActionGrantRow.action == "admit-users"
                    )
                )
        outcome = await waiter
    assert isinstance(outcome, ConflictError if turn == "identity" else AccessDeniedError)
    async with database.session() as session:
        assert (
            await session.get(
                HumanIdentityLinkRow, (_identity(seed).authority.value, str(BOB_IDENTITY_ID))
            )
            is None
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )


async def test_identity_lock_wait_stays_within_the_existing_database_deadline(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    async with (
        asyncio.timeout(20),
        asyncio.TaskGroup() as tasks,
        database.session() as holder,
        holder.begin(),
    ):
        await PostgresIdentityCoordinator(holder).acquire(
            installation_id=seed.binding.installation_id, identity=_identity(seed)
        )
        pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
        assert pid is not None
        waiter = tasks.create_task(_attempt(database, seed))
        await _wait_for_waiter(database, pid, waiter)
        assert isinstance(await waiter, DependencyUnavailableError)
    await _assert_no_bob(database, seed)


@pytest.mark.parametrize("scope", ["actor", "identity", "installation"])
async def test_result_reader_refuses_a_different_original_binding(
    database: Database, scope: str
) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed)
    async with database.session() as session, session.begin():
        with pytest.raises(ConflictError):
            await PostgresHumanAdmissionResultReader(session).original(
                installation_id=type(first.installation_id)(uuid4())
                if scope == "installation"
                else first.installation_id,
                identity=replace(first.identity, subject=IdentitySubject(str(uuid4())))
                if scope == "identity"
                else first.identity,
                organization_id=first.organization_id,
                actor_id=PrincipalId(uuid4()) if scope == "actor" else first.actor_principal_id,
                operation=replace(first.operation, created=False),
            )


async def test_writer_rejects_completed_parent_without_duplicate_audit_or_state_change(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await _admit(database, seed)
    async with database.session() as session, session.begin():
        facts = await PostgresHumanAdmissionFactsReader(session).read_for_admission(
            access=seed.access, organization_id=seed.organization_id, identity=_identity(seed)
        )
        assert facts is not None and facts.principal is not None
        with pytest.raises(ConflictError):
            await PostgresHumanAdmissionWriter(session).save(
                facts=facts,
                principal=facts.principal,
                actor_id=seed.access.actor_principal_id,
                operation_id=first.operation.operation_id,
            )
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == first.operation.operation_id.value)
            )
            == 1
        )
