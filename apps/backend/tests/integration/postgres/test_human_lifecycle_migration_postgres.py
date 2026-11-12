"""Qualify lifecycle backing independently of writes, worker dispatch or provider evidence."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import String, delete, inspect, literal, select, update
from sqlalchemy.exc import IntegrityError
from tests.integration.access.test_project_deletion_postgres import (
    admit_deletion,
    seed_deletion_scenario,
)
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, seed_project_creator

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.human_lifecycle_operation_result_row import (
    HumanLifecycleOperationResultRow,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


@pytest_asyncio.fixture
async def scope(database: Database) -> ProjectCreationSeedDTO:
    return await seed_project_creator(database)


def _obligation(scope: ProjectCreationSeedDTO) -> HumanSuspensionObligationRow:
    now = datetime.now(UTC)
    return HumanSuspensionObligationRow(
        id=uuid4(),
        job_id=uuid4(),
        operation_id="suspend-" + str(uuid4()),
        request_id=uuid4(),
        installation_id=scope.binding.installation_id.value,
        organization_id=scope.organization_id.value,
        principal_id=scope.access.actor_principal_id.value,
        initiator_principal_id=scope.access.actor_principal_id.value,
        authority=scope.binding.identity.authority.value,
        subject=scope.binding.identity.subject.value,
        request_key="original-suspension",
        request_fingerprint=b"f" * 32,
        before_access_revision=4,
        access_revision=5,
        admitted_at=now,
        queued_deadline=now + timedelta(hours=24),
    )


def _result(
    scope: ProjectCreationSeedDTO,
    parent: HumanSuspensionObligationRow | None,
    *,
    action: OrganizationAction = OrganizationAction.SUSPEND_USERS,
    changed: bool = True,
) -> HumanLifecycleOperationResultRow:
    return HumanLifecycleOperationResultRow(
        operation_id=parent.operation_id
        if parent is not None and changed and action is OrganizationAction.SUSPEND_USERS
        else "result-" + str(uuid4()),
        installation_id=scope.binding.installation_id.value,
        organization_id=scope.organization_id.value,
        principal_id=scope.access.actor_principal_id.value,
        actor_principal_id=scope.access.actor_principal_id.value,
        action_id=action,
        before_revision=7,
        access_revision=7 + int(changed),
        changed=changed,
        cleanup_operation_id=parent.id if parent is not None else None,
        before_credential_version=2 if action is OrganizationAction.RESTORE_USERS else None,
        credential_version=2 + int(changed) if action is OrganizationAction.RESTORE_USERS else None,
    )


def _native(
    result: HumanLifecycleOperationResultRow, parent: HumanSuspensionObligationRow | None
) -> IdempotencyReservationRow:
    verb = "suspend" if result.action_id is OrganizationAction.SUSPEND_USERS else "restore"
    row = IdempotencyReservationRow(
        operation_id=result.operation_id,
        principal_id=result.actor_principal_id,
        organization_id=result.organization_id,
        project_id=None,
        method="POST",
        requested_route=f"/v1/organizations/{result.organization_id}/humans/{result.principal_id}/{verb}",
        request_key=parent.request_key
        if parent is not None and result.operation_id == parent.operation_id
        else "result-" + str(uuid4()),
        request_fingerprint=b"f" * 32,
        replay_kind=OperationReplayKind.ASYNC_JOB
        if verb == "suspend"
        else OperationReplayKind.SAFE_RESULT,
        expires_at=None if verb == "suspend" else datetime.now(UTC) + timedelta(hours=24),
    )
    row.state = OperationReservationState.REPLAYABLE
    return row


def _configuration(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


@pytest.mark.parametrize(
    "table_name", ["human_suspension_obligations", "human_lifecycle_operation_results"]
)
async def test_original_lifecycle_storage_is_available(database: Database, table_name: str) -> None:
    async with database.session() as session:
        connection = await session.connection()
        assert await connection.run_sync(lambda sync: inspect(sync).has_table(table_name)), (
            f"Required original lifecycle storage is missing: {table_name}"
        )


@pytest.mark.parametrize(
    "invalid", ["duplicate", "missing-original", "cross-mode", "partial-repeat"]
)
async def test_maintenance_storage_preserves_one_repeat_even_after_consumption(
    database: Database, scope: ProjectCreationSeedDTO, invalid: str
) -> None:
    parent = _obligation(scope)
    fence = uuid4()

    def receipt(request: str) -> HostMaintenanceReceiptRow:
        return HostMaintenanceReceiptRow(
            installation_id=parent.installation_id,
            operator_request_id=request,
            authority=parent.authority,
            subject=parent.subject,
            mode="human-suspension-cleanup",
            outcome="requeued",
            recovery_operation_id=None,
            released=None,
            run_id=None,
            deadline=None,
            operator_label="Operator",
            reason="Repeat exact retained step",
            authorized_at=parent.admitted_at,
            suspension_obligation_id=parent.id,
            suspension_repeat_step="hydra_cli_grants",
            suspension_repeat_attempt=1,
            suspension_repeat_fence=fence,
        )

    async with database.session() as session, session.begin():
        session.add(parent)
        await session.flush()
        first = receipt("original-repeat")
        first.suspension_repeat_consumed_at = parent.admitted_at + timedelta(seconds=1)
        session.add(first)

    second = receipt("second-request")
    if invalid == "missing-original":
        second.suspension_obligation_id = uuid4()
    elif invalid == "cross-mode":
        second.mode = "bootstrap-first-administrator"
        second.outcome = "bootstrapped"
    elif invalid == "partial-repeat":
        second.suspension_repeat_fence = None
    with pytest.raises(IntegrityError) as failure:
        async with database.session() as session, session.begin():
            session.add(second)
            await session.flush()
    assert {
        "duplicate": "uq_maintenance_suspension_repeat",
        "missing-original": "fk_maintenance_suspension_original",
        "cross-mode": "ck_maintenance_result",
        "partial-repeat": "ck_maintenance_result",
    }[invalid] in str(failure.value.orig)

    async with database.session() as session:
        saved = await session.get(
            HostMaintenanceReceiptRow, (parent.installation_id, "original-repeat")
        )
        assert saved is not None and saved.suspension_repeat_fence == fence
        assert saved.suspension_repeat_consumed_at is not None


async def test_pending_original_has_fixed_identity_without_native_or_child(
    database: Database, scope: ProjectCreationSeedDTO
) -> None:
    parent = _obligation(scope)
    async with database.session() as session, session.begin():
        session.add(parent)
        await session.flush()
        assert await session.get(DurableJobRow, parent.job_id) is None
        assert await session.get(IdempotencyReservationRow, parent.operation_id) is None
    async with database.session() as session:
        stored = await session.get(HumanSuspensionObligationRow, parent.id)
        assert stored is not None
        assert (
            stored.job_id,
            stored.operation_id,
            stored.installation_id,
            stored.authority,
            stored.subject,
        ) == (
            parent.job_id,
            parent.operation_id,
            scope.binding.installation_id.value,
            scope.binding.identity.authority.value,
            scope.binding.identity.subject.value,
        )
        assert stored.queued_deadline == stored.admitted_at + timedelta(hours=24)
        assert stored.queue_exhausted_at is None
        assert (
            stored.kratos_sessions,
            stored.hydra_cli_grants,
            stored.hydra_remembered_logins,
        ) == (
            IdentityRecoveryCleanupState.PENDING,
            IdentityRecoveryCleanupState.PENDING,
            IdentityRecoveryCleanupState.PENDING,
        )


@pytest.mark.parametrize(
    "action", [OrganizationAction.SUSPEND_USERS, OrganizationAction.RESTORE_USERS]
)
@pytest.mark.parametrize("changed", [False, True])
async def test_safe_original_round_trip_preserves_scope_and_delta(
    database: Database, scope: ProjectCreationSeedDTO, action: OrganizationAction, changed: bool
) -> None:
    parent = _obligation(scope)
    original = _result(scope, parent, action=action, changed=changed)
    async with database.session() as session, session.begin():
        session.add(parent)
        session.add(_native(original, parent))
        await session.flush()
        session.add(original)
    async with database.session() as session:
        stored = await session.get(HumanLifecycleOperationResultRow, original.operation_id)
        assert stored is not None
        assert (
            stored.installation_id,
            stored.organization_id,
            stored.principal_id,
            stored.actor_principal_id,
        ) == (
            scope.binding.installation_id.value,
            scope.organization_id.value,
            scope.access.actor_principal_id.value,
            scope.access.actor_principal_id.value,
        )
        assert stored.action_id is action and stored.changed is changed
        assert stored.access_revision == stored.before_revision + int(changed)
        assert stored.cleanup_operation_id == parent.id
        if action is OrganizationAction.RESTORE_USERS:
            assert stored.credential_version == 2 + int(changed)
        else:
            assert stored.credential_version is None


@pytest.mark.parametrize(
    "wrong", ["operation", "actor", "organization", "target", "cleanup", "installation"]
)
async def test_original_requires_its_exact_native_and_cleanup_scope(
    database: Database, scope: ProjectCreationSeedDTO, wrong: str
) -> None:
    parent = _obligation(scope)
    original = _result(scope, parent)
    native = _native(original, parent)
    match wrong:
        case "operation":
            original.operation_id = "missing-native"
        case "actor":
            original.actor_principal_id = uuid4()
        case "organization":
            original.organization_id = uuid4()
        case "target":
            original.principal_id = uuid4()
        case "cleanup":
            original.cleanup_operation_id = uuid4()
        case _:
            original.installation_id = uuid4()
    async with database.session() as session, session.begin():
        session.add_all([parent, native])
        await session.flush()
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(original)
                await session.flush()


@pytest.mark.parametrize(
    "wrong",
    [
        "negative-revision",
        "revision-delta",
        "source-revision",
        "fingerprint",
        "queue-window",
        "exhaustion-and-completion",
        "early-exhaustion",
        "unconfirmed-completion",
        "unknown-outcome",
    ],
)
async def test_obligation_rejects_invalid_original_or_progress_shape(
    database: Database, scope: ProjectCreationSeedDTO, wrong: str
) -> None:
    parent = _obligation(scope)
    async with database.session() as session, session.begin():
        session.add(parent)
        await session.flush()
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                match wrong:
                    case "negative-revision":
                        parent.before_access_revision = -1
                    case "revision-delta":
                        parent.access_revision += 1
                    case "source-revision":
                        parent.source_revision = 0
                    case "fingerprint":
                        parent.request_fingerprint = b"short"
                    case "queue-window":
                        parent.queued_deadline += timedelta(seconds=1)
                    case "exhaustion-and-completion":
                        parent.queue_exhausted_at = parent.queued_deadline
                        parent.kratos_sessions = IdentityRecoveryCleanupState.CONFIRMED
                        parent.hydra_cli_grants = IdentityRecoveryCleanupState.CONFIRMED
                        parent.hydra_remembered_logins = IdentityRecoveryCleanupState.CONFIRMED
                        parent.completed_at = parent.queued_deadline
                    case "early-exhaustion":
                        parent.queue_exhausted_at = parent.admitted_at
                    case "unconfirmed-completion":
                        parent.completed_at = parent.admitted_at
                    case _:
                        await session.execute(
                            update(HumanSuspensionObligationRow)
                            .where(HumanSuspensionObligationRow.id == parent.id)
                            .values(kratos_sessions=literal("invalid", type_=String()))
                        )
                await session.flush()


@pytest.mark.parametrize(
    "wrong",
    ["revision-delta", "unsafe-revision", "suspension-version", "zero-version", "version-delta"],
)
async def test_safe_original_rejects_unsafe_revision_or_version_shape(
    database: Database, scope: ProjectCreationSeedDTO, wrong: str
) -> None:
    parent = _obligation(scope)
    restoration = wrong in ("zero-version", "version-delta")
    original = _result(
        scope,
        parent,
        action=OrganizationAction.RESTORE_USERS
        if restoration
        else OrganizationAction.SUSPEND_USERS,
    )
    async with database.session() as session, session.begin():
        session.add_all([parent, _native(original, parent)])
        await session.flush()
        match wrong:
            case "revision-delta":
                original.access_revision += 1
            case "unsafe-revision":
                original.access_revision = 9007199254740992
            case "suspension-version":
                original.before_credential_version = 1
                original.credential_version = 2
            case "zero-version":
                original.credential_version = 0
            case _:
                original.credential_version = 4
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(original)
                await session.flush()


@pytest.mark.parametrize("duplicate", ["job", "operation"])
async def test_original_job_and_operation_identity_are_unique(
    database: Database, scope: ProjectCreationSeedDTO, duplicate: str
) -> None:
    first, second = _obligation(scope), _obligation(scope)
    if duplicate == "job":
        second.job_id = first.job_id
    else:
        second.operation_id = first.operation_id
    async with database.session() as session, session.begin():
        session.add(first)
        await session.flush()
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(second)
                await session.flush()


async def test_native_and_live_link_removal_do_not_erase_original_obligation(
    database: Database, scope: ProjectCreationSeedDTO
) -> None:
    parent = _obligation(scope)
    original = _result(scope, parent)
    async with database.session() as session, session.begin():
        session.add_all([parent, _native(original, parent)])
        await session.flush()
        session.add(original)
        await session.flush()
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == original.operation_id
            )
        )
        await session.execute(
            delete(HumanIdentityLinkRow).where(
                HumanIdentityLinkRow.principal_id == scope.access.actor_principal_id.value
            )
        )
    async with database.session() as session:
        assert await session.get(HumanLifecycleOperationResultRow, original.operation_id) is None
        retained = await session.get(HumanSuspensionObligationRow, parent.id)
        assert retained is not None and retained.job_id == parent.job_id
        assert retained.subject == scope.binding.identity.subject.value


@pytest.mark.parametrize("retained", ["obligation", "result", "child"])
async def test_retained_lifecycle_storage_refuses_destructive_downgrade(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    scope: ProjectCreationSeedDTO,
    retained: str,
) -> None:
    parent = _obligation(scope)
    original = _result(scope, None, action=OrganizationAction.RESTORE_USERS)
    async with database.session() as session, session.begin():
        if retained in {"obligation", "child"}:
            session.add(parent)
            if retained == "child":
                await session.flush()
                session.add(_suspension_child(parent))
        else:
            session.add(_native(original, None))
            await session.flush()
            session.add(original)
    with pytest.raises(RuntimeError, match="Retained human lifecycle"):
        command.downgrade(
            _configuration(temporary_postgres_settings), "0033_stranded_authority_repair"
        )
    async with database.session() as session:
        assert await session.scalar(select(AlembicVersionRow.version_num)) == "0034_human_lifecycle"
        if retained in {"obligation", "child"}:
            assert await session.get(HumanSuspensionObligationRow, parent.id) is not None
            if retained == "child":
                assert await session.get(DurableJobRow, parent.job_id) is not None
        else:
            assert (
                await session.get(HumanLifecycleOperationResultRow, original.operation_id)
                is not None
            )


async def test_empty_downgrade_preserves_actual_project_deletion_backing(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    existing = await seed_deletion_scenario(database)
    accepted = await admit_deletion(database, existing)
    command.downgrade(_configuration(temporary_postgres_settings), "0033_stranded_authority_repair")
    command.upgrade(_configuration(temporary_postgres_settings), "head")
    async with database.session() as session:
        assert (
            await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
            is not None
        )
        assert await session.get(DurableJobRow, accepted.job_id.value) is not None
        assert list(await session.scalars(select(HumanSuspensionObligationRow.id))) == []
        assert (
            list(await session.scalars(select(HumanLifecycleOperationResultRow.operation_id))) == []
        )


def _suspension_child(parent: HumanSuspensionObligationRow) -> DurableJobRow:
    return DurableJobRow(
        id=parent.job_id,
        operation_id=None,
        request_id=parent.request_id,
        installation_id=parent.installation_id,
        principal_id=None,
        principal_kind=None,
        organization_id=parent.organization_id,
        project_id=None,
        action_id=None,
        payload_kind="human.suspension-cleanup",
        payload_version=1,
        payload=parent.id.bytes,
        admitted_at=parent.admitted_at,
        queued_deadline=parent.queued_deadline,
        due_at=parent.admitted_at,
        binding_kind="human_suspension",
        suspension_obligation_id=parent.id,
    )


@pytest.mark.parametrize(
    "mismatch",
    [
        None,
        "job",
        "request",
        "installation",
        "organization",
        "project",
        "old-product",
        "old-artifact",
        "old-deletion",
    ],
)
async def test_closed_job_binding_accepts_only_exact_organization_only_suspension(
    database: Database, scope: ProjectCreationSeedDTO, mismatch: str | None
) -> None:
    parent = _obligation(scope)
    async with database.session() as session, session.begin():
        session.add(parent)
    job = _suspension_child(parent)
    match mismatch:
        case "job":
            job = replace(job, id=uuid4())
        case "request":
            job = replace(job, request_id=uuid4())
        case "installation":
            job = replace(job, installation_id=uuid4())
        case "organization":
            job = replace(job, organization_id=uuid4())
        case "project":
            job = replace(job, project_id=uuid4())
        case "old-product":
            job = replace(
                job,
                binding_kind="product",
                suspension_obligation_id=None,
                operation_id=parent.operation_id,
                principal_id=parent.principal_id,
                principal_kind="human",
                action_id="inspect-feedback",
            )
        case "old-artifact":
            job = replace(
                job,
                binding_kind="artifact_cleanup",
                suspension_obligation_id=None,
                cleanup_obligation_id=uuid4(),
            )
        case "old-deletion":
            job = replace(
                job,
                binding_kind="project_deletion",
                suspension_obligation_id=None,
                deletion_obligation_id=uuid4(),
            )
        case _:
            assert mismatch is None
    if mismatch is not None:
        constraint = (
            "fk_job_human_suspension_scope"
            if mismatch in {"job", "request", "installation", "organization"}
            else "ck_job_closed_binding"
        )
        with pytest.raises(IntegrityError, match=constraint):
            async with database.session() as session, session.begin():
                session.add(job)
        return
    async with database.session() as session, session.begin():
        session.add(job)
    async with database.session() as session:
        stored = await session.get(DurableJobRow, parent.job_id)
        assert stored is not None and stored.suspension_obligation_id == parent.id
        assert stored.project_id is None and stored.operation_id is None
        assert await session.get(IdempotencyReservationRow, parent.operation_id) is None
