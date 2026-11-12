"""Exercise retained human suspension cleanup ownership against PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, delete, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.maintenance_command import run_maintenance
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    seed_membership_project,
)
from tests.support.recovery_notifications import notification_service
from tests.support.spending_scenarios import wait_for_database_lock

from inframeld_backend.access.application.commands.human_suspension_cleanup_maintenance_command import (
    HumanSuspensionCleanupMaintenanceCommand,
)
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_cleanup_maintenance_result_dto import (
    HumanSuspensionCleanupMaintenanceResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_continue_outcome import (
    HumanSuspensionCleanupContinueOutcome,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_execution_state import (
    HumanSuspensionCleanupExecutionState,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_error_code import (
    HumanSuspensionCleanupMaintenanceErrorCode,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_intent import (
    HumanSuspensionCleanupMaintenanceIntent,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.recovery_maintenance_error_code import (
    RecoveryMaintenanceErrorCode,
)
from inframeld_backend.access.application.errors.human_suspension_cleanup_maintenance_error import (
    HumanSuspensionCleanupMaintenanceError,
)
from inframeld_backend.access.application.errors.recovery_maintenance_error import (
    RecoveryMaintenanceError,
)
from inframeld_backend.access.application.services.human_lifecycle_fingerprint_service import (
    HumanLifecycleFingerprintService,
)
from inframeld_backend.access.application.services.human_suspension_cleanup_maintenance_service import (
    HumanSuspensionCleanupMaintenanceService,
)
from inframeld_backend.access.application.services.human_suspension_service import (
    HumanSuspensionService,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.access.application.value_objects.identity_settings_flow_id import (
    IdentitySettingsFlowId,
)
from inframeld_backend.access.application.value_objects.suspension_reason import SuspensionReason
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_human_lifecycle_facts_reader import (
    PostgresHumanLifecycleFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_lifecycle_result_reader import (
    PostgresHumanLifecycleResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_facts_reader import (
    PostgresIdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_resume_facts_reader import (
    PostgresIdentityRecoveryCleanupResumeFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_human_suspension_cleanup_maintenance_repository import (
    PostgresHumanSuspensionCleanupMaintenanceRepository,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
    SqlAlchemyRecoveryTransactionManager,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.writers.postgres_human_lifecycle_writer import (
    PostgresHumanLifecycleWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_writer import (
    PostgresIdentityRecoveryCleanupWriter,
)
from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.human_suspension_cleanup_step import (
    HumanSuspensionCleanupStep,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.human_suspension_job_authorization_service import (
    HumanSuspensionJobAuthorizationService,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.readers.postgres_human_suspension_job_facts_reader import (
    PostgresHumanSuspensionJobFactsReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.writers.postgres_human_suspension_cleanup_checkpoint_writer import (
    PostgresHumanSuspensionCleanupCheckpointWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_human_suspension_cleanup_claim_writer import (
    PostgresHumanSuspensionCleanupClaimWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


async def _suspend_for_cleanup(
    database: Database, scope: MembershipProjectSeedDTO
) -> HumanSuspensionResultDTO:
    actor = scope.actor
    organization = actor.organization_id.value
    target = scope.bob_id.value
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(OrganizationRow.id == organization)
        )
    assert revision is not None
    async with database.session() as session:
        return await HumanSuspensionService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            lifecycle_facts_reader=PostgresHumanLifecycleFactsReader(session),
            lifecycle_writer=PostgresHumanLifecycleWriter(session),
            lifecycle_result_reader=PostgresHumanLifecycleResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            lifecycle_fingerprint_service=HumanLifecycleFingerprintService(
                RequestFingerprintService(RequestFingerprintKey(b"H" * 32))
            ),
        ).suspend(
            access=actor.access,
            command=SuspendHumanCommand(
                actor.organization_id, scope.bob_id, revision, SuspensionReason("Incident reviewed")
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/organizations/{organization}/humans/{target}/suspend",
                IdempotencyKey("live-suspension-attempt"),
            ),
            request_id=RequestId(uuid4()),
        )


async def _live_suspension_attempt(
    database: Database, *, scope: MembershipProjectSeedDTO | None = None
) -> tuple[JobAttemptContextDTO, UUID]:
    if scope is None:
        scope = await seed_membership_project(database)
    accepted = await _suspend_for_cleanup(database, scope)
    worker_id = uuid4()
    fence = JobFence(uuid4())
    async with database.session() as session, session.begin():
        parent = await session.get(
            HumanSuspensionObligationRow, UUID(accepted.cleanup_operation_id.value)
        )
        assert parent is not None
        binding = PostgresJobBindingMapper.human_suspension(parent)
        assert binding.operation_id == accepted.operation.operation_id
        row = await session.get(DurableJobRow, binding.job_id.value)
        assert row is not None and row.status == JobStatus.QUEUED.value and row.attempt_count == 0
        assert row.binding_kind == "human_suspension" and row.suspension_obligation_id == parent.id
        payload = JobPayload(row.payload_kind, row.payload_version, row.payload)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        deadline = now + timedelta(minutes=2)
        # Install the exact test-owned attempt while production dispatch stays dormant.
        row.status = JobStatus.RUNNING.value
        row.attempt_count = 1
        row.worker_id = worker_id
        row.fence = fence.value
        row.lease_expires_at = now + timedelta(seconds=30)
        row.work_deadline = deadline
        session.add(
            DurableJobAttemptRow(
                job_id=row.id, number=1, fence=fence.value, worker_id=worker_id, started_at=now
            )
        )
    return JobAttemptContextDTO(
        binding.job_id, binding, payload, 1, fence, deadline, b""
    ), worker_id


async def _queued_suspension_binding(
    database: Database, scope: MembershipProjectSeedDTO
) -> HumanSuspensionJobBindingDTO:
    accepted = await _suspend_for_cleanup(database, scope)
    async with database.session() as session:
        parent = await session.get(
            HumanSuspensionObligationRow, UUID(accepted.cleanup_operation_id.value)
        )
        assert parent is not None
        binding = PostgresJobBindingMapper.human_suspension(parent)
        assert binding.operation_id == accepted.operation.operation_id
        return binding


async def _claim_private(
    session: AsyncSession,
    binding: HumanSuspensionJobBindingDTO,
    worker_id: UUID,
    *,
    work_seconds: float = 120,
) -> JobAttemptContextDTO | None:
    return await PostgresHumanSuspensionCleanupClaimWriter(
        session, installation_id=binding.installation_id, authority=binding.identity.authority
    ).claim_next(worker_id=worker_id, lease_seconds=30, work_seconds=work_seconds)


async def _admit_routine_cleanup(
    database: Database, binding: HumanSuspensionJobBindingDTO
) -> OperationId:
    authority = binding.identity.authority
    event = IdentityRecoveryEventDTO(
        IdentityRecoveryFlowId(uuid4()),
        VerifiedHumanIdentityDTO(authority, IdentitySubject(str(uuid4()))),
        IdentityRecoveryEventKind.RECOVERY,
    )
    evidence = IdentityRecoverySettingsEvidenceDTO(
        event.identity, IdentitySettingsFlowId(uuid4()), IdentitySessionId(uuid4()), event.flow_id
    )
    async with database.session() as session:
        notifications = notification_service(session, binding.installation_id, authority)
        admitted = await notifications.admit(event)
        await notifications.associate_settings(evidence)
        await notifications.record_password_saved(evidence)
        return admitted.operation_id


def _routine_reader(
    session: AsyncSession, binding: HumanSuspensionJobBindingDTO
) -> PostgresIdentityRecoveryCleanupFactsReader:
    return PostgresIdentityRecoveryCleanupFactsReader(
        session, installation_id=binding.installation_id, authority=binding.identity.authority
    )


async def _claim_routine(
    session: AsyncSession, binding: HumanSuspensionJobBindingDTO, operation_id: OperationId
) -> IdentityRecoveryCleanupClaimDTO | None:
    reader = _routine_reader(session, binding)
    candidate = await reader.next_candidate()
    if candidate is None:
        return None
    assert candidate == operation_id
    work = await reader.lock_work(candidate)
    now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
    assert work is not None and work.has_original_password_receipt and now is not None
    claim = IdentityRecoveryCleanupClaimDTO(
        candidate, work.run.id, uuid4(), uuid4(), uuid4(), now + timedelta(seconds=60)
    )
    await PostgresIdentityRecoveryCleanupWriter(
        session, installation_id=binding.installation_id, authority=binding.identity.authority
    ).claim(work, claim, at=now)
    return claim


@pytest.mark.asyncio
async def test_suspension_claim_uses_its_fixed_job_with_an_ordinary_attempt_running(
    database: Database,
) -> None:
    scope = await seed_membership_project(database)
    actor = scope.actor
    authority = AdmittedWorkAuthorityDTO(
        principal_id=actor.access.actor_principal_id,
        principal_kind=PrincipalKind.HUMAN,
        installation_id=actor.binding.installation_id,
        organization_id=actor.organization_id,
        project_id=scope.project.project_id,
        action_id=ActionId("inspect-feedback"),
        human_binding=actor.binding,
    )
    async with database.session() as session, session.begin():
        reservations = PostgresOperationReservationWriter(session)
        original = await reservations.reserve(
            OperationReservationRequestDTO(
                authority.principal_id,
                authority.organization_id,
                authority.project_id,
                HttpMethod.POST,
                f"/test/projects/{authority.project_id.value}/feedback-reports",
                IdempotencyKey("occupied-ordinary-slot"),
                b"J" * 32,
            )
        )
        store = PostgresJobStore(session)
        admitted = await store.admit(
            operation_id=original.operation_id,
            request_id=RequestId(uuid4()),
            authority=authority,
            payload=JobPayload("test.progress", 1, b"fixed"),
            capacity=1,
        )
        await reservations.mark_replayable(original.operation_id, OperationReplayKind.ASYNC_JOB)
        ordinary = await store.next_candidate()
        assert ordinary is not None and ordinary.job_id == admitted.job_id
        ordinary_attempt = await store.start_attempt(
            ordinary, worker_id=uuid4(), lease_seconds=30, work_seconds=120
        )
        assert not await store.has_fresh_capacity(capacity=1)

    accepted = await _suspend_for_cleanup(database, scope)
    async with database.session() as session:
        parent = await session.get(
            HumanSuspensionObligationRow, UUID(accepted.cleanup_operation_id.value)
        )
        assert parent is not None
        binding = PostgresJobBindingMapper.human_suspension(parent)
        child = await session.get(DurableJobRow, binding.job_id.value)
        ordinary_row = await session.get(DurableJobRow, ordinary_attempt.job_id.value)
        assert child is not None and child.status == JobStatus.QUEUED.value
        assert child.attempt_count == 0 and child.work_deadline is None
        assert ordinary_row is not None and ordinary_row.status == JobStatus.RUNNING.value
        assert ordinary_row.fence == ordinary_attempt.fence.value
        assert binding.operation_id == accepted.operation.operation_id
        schedule = child.admitted_at, child.queued_deadline, child.due_at
        payload = JobPayload(child.payload_kind, child.payload_version, child.payload)

    worker_id = uuid4()
    async with database.session() as session, session.begin():
        claimed = await PostgresHumanSuspensionCleanupClaimWriter(
            session, installation_id=binding.installation_id, authority=binding.identity.authority
        ).claim_next(worker_id=worker_id, lease_seconds=30, work_seconds=120)

    assert claimed is not None and claimed.attempt == 1
    assert (claimed.job_id, claimed.binding, claimed.payload) == (binding.job_id, binding, payload)
    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, binding.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, claimed.attempt))
        ordinary_row = await session.get(DurableJobRow, ordinary_attempt.job_id.value)
        assert child is not None and attempt is not None and ordinary_row is not None
        assert child.status == JobStatus.RUNNING.value and child.attempt_count == 1
        assert child.worker_id == attempt.worker_id == worker_id
        assert child.fence == attempt.fence == claimed.fence.value
        assert attempt.ended_at is None and child.pending_effect is None
        assert (child.admitted_at, child.queued_deadline, child.due_at) == schedule
        assert schedule[0] <= attempt.started_at < schedule[1]
        assert (
            child.work_deadline
            == claimed.work_deadline
            == attempt.started_at + timedelta(seconds=120)
        )
        assert child.lease_expires_at is not None
        assert (
            attempt.started_at
            < child.lease_expires_at
            <= attempt.started_at + timedelta(seconds=30)
        )
        assert ordinary_row.status == JobStatus.RUNNING.value
        assert ordinary_row.fence == ordinary_attempt.fence.value
        await HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        ).require_current(claimed, worker_id=worker_id)


@pytest.mark.asyncio
async def test_live_suspension_attempt_defers_eligible_routine_recovery(database: Database) -> None:
    suspended, worker_id = await _live_suspension_attempt(database)
    assert isinstance(suspended.binding, HumanSuspensionJobBindingDTO)
    binding = suspended.binding
    operation_id = await _admit_routine_cleanup(database, binding)

    async with database.session() as session, session.begin():
        await HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        ).require_current(suspended, worker_id=worker_id)
    async with database.session() as session, session.begin():
        work = await _routine_reader(session, binding).lock_work(operation_id)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert work is not None and now is not None
        assert work.has_original_password_receipt and work.credential_version is not None
        assert work.run.next_attempt_at <= now < work.run.deadline
        assert work.claim is None and work.run.consumed_attempts == 0
        original_run = work.run

    async with database.session() as session, session.begin():
        candidate = await _routine_reader(session, binding).next_candidate()
        assert candidate is None, "A live suspension attempt must occupy the shared recovery slot."

    async with database.session() as session, session.begin():
        work = await _routine_reader(session, binding).lock_work(operation_id)
        assert work is not None and work.claim is None and work.run == original_run


@pytest.mark.asyncio
@pytest.mark.parametrize("first_family", ["routine", "suspension"])
@pytest.mark.parametrize("commit_first", [True, False], ids=["commit", "rollback"])
async def test_competing_recovery_claim_waits_and_rechecks_the_other_family(
    database: Database, first_family: str, commit_first: bool
) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    operation_id = await _admit_routine_cleanup(database, binding)

    async def claim_other() -> JobAttemptContextDTO | IdentityRecoveryCleanupClaimDTO | None:
        async with database.session() as session, session.begin():
            if first_family == "routine":
                return await _claim_private(session, binding, uuid4())
            return await _claim_routine(session, binding, operation_id)

    async with asyncio.TaskGroup() as tasks, database.session() as holder, holder.begin() as first:
        if first_family == "routine":
            assert await _claim_routine(holder, binding, operation_id) is not None
        else:
            assert await _claim_private(holder, binding, uuid4()) is not None
        other = tasks.create_task(claim_other())
        await wait_for_database_lock(database, other)
        if not commit_first:
            await first.rollback()

    assert (other.result() is None) == commit_first
    routine_won = (first_family == "routine") == commit_first
    async with database.session() as session, session.begin():
        work = await _routine_reader(session, binding).lock_work(operation_id)
        child = await session.get(DurableJobRow, binding.job_id.value)
        assert work is not None and child is not None
        assert (work.claim is not None) == routine_won
        assert work.run.consumed_attempts == int(routine_won)
        assert child.attempt_count == int(not routine_won)
        assert child.status == (JobStatus.QUEUED.value if routine_won else JobStatus.RUNNING.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("unresolved", [False, True], ids=["safe-backoff", "ambiguous"])
async def test_expired_suspension_claim_keeps_its_original_and_fences_replacement(
    database: Database, unresolved: bool
) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    first_worker, replacement_worker = uuid4(), uuid4()
    async with database.session() as session, session.begin():
        first = await _claim_private(session, binding, first_worker)
        assert first is not None
    await _commit_cleanup_step(
        database, first, first_worker, HumanSuspensionCleanupStep.KRATOS_SESSIONS
    )
    marker = None
    if unresolved:
        async with database.session() as session, session.begin():
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                first, worker_id=first_worker, step=HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS
            )
        marker = f"hydra_cli_grants:{first.attempt}:{first.fence.value}"

    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, binding.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, first.attempt))
        assert child is not None and attempt is not None
        assert child.pending_effect == marker
        original_admission = child.admitted_at, child.queued_deadline
        child.lease_expires_at = attempt.started_at

    async with database.session() as session, session.begin():
        assert await _claim_private(session, binding, replacement_worker) is None

    async with database.session() as session, session.begin():
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        child = await session.get(DurableJobRow, binding.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, first.attempt))
        assert parent is not None and child is not None and attempt is not None
        assert parent.completed_at is None and parent.queue_exhausted_at is None
        assert parent.kratos_sessions is IdentityRecoveryCleanupState.CONFIRMED
        assert parent.hydra_cli_grants is IdentityRecoveryCleanupState.PENDING
        assert (child.admitted_at, child.queued_deadline) == original_admission
        assert child.work_deadline == first.work_deadline
        assert child.pending_effect == marker and child.attempt_count == 1
        assert child.worker_id is None and child.fence is None and child.lease_expires_at is None
        assert attempt.worker_id == first_worker and attempt.fence == first.fence.value
        assert attempt.ended_at is not None
        closed_at = attempt.ended_at
        if unresolved:
            assert child.status == JobStatus.RECOVERY_REQUIRED.value
            assert attempt.reason == child.reason == "provider_outcome_uncertain"
            assert child.terminal_at == closed_at
        else:
            assert child.status == JobStatus.QUEUED.value and child.terminal_at is None
            assert child.due_at == closed_at + timedelta(seconds=5)
        authorizer = HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        )
        with pytest.raises(AccessDeniedError):
            await authorizer.require_current(first, worker_id=first_worker)

    if unresolved:
        async with database.session() as session, session.begin():
            assert await _claim_private(session, binding, replacement_worker) is None
            assert await session.get(DurableJobAttemptRow, (binding.job_id.value, 2)) is None
        return

    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, binding.job_id.value)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert child is not None and now is not None
        child.due_at = now + timedelta(seconds=30)
    async with database.session() as session, session.begin():
        assert await _claim_private(session, binding, replacement_worker) is None

    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, binding.job_id.value)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert child is not None and now is not None
        child.due_at = now
    async with database.session() as session, session.begin():
        replacement = await _claim_private(session, binding, replacement_worker, work_seconds=60)
        assert replacement is not None and replacement.attempt == 2
        assert (replacement.job_id, replacement.binding, replacement.payload) == (
            first.job_id,
            first.binding,
            first.payload,
        )
        assert replacement.work_deadline == first.work_deadline and replacement.fence != first.fence
    async with database.session() as session, session.begin():
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, 1))
        assert attempt is not None and attempt.ended_at == closed_at
        authorizer = HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        )
        await authorizer.require_current(replacement, worker_id=replacement_worker)
        with pytest.raises(AccessDeniedError):
            await authorizer.require_current(first, worker_id=first_worker)


@pytest.mark.asyncio
async def test_unstarted_private_cleanup_retains_original_queue_exhaustion(
    database: Database,
) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    async with database.session() as session, session.begin():
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        child = await session.get(DurableJobRow, binding.job_id.value)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert parent is not None and child is not None and now is not None
        deadline = now - timedelta(seconds=1)
        admitted = deadline - timedelta(hours=24)
        parent.admitted_at, parent.queued_deadline = admitted, deadline
        child.admitted_at, child.queued_deadline, child.due_at = admitted, deadline, admitted

    async with database.session() as session, session.begin():
        assert await _claim_private(session, binding, uuid4()) is None
    async with database.session() as session, session.begin():
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        child = await session.get(DurableJobRow, binding.job_id.value)
        assert parent is not None and child is not None
        assert parent.queue_exhausted_at is not None and parent.queue_exhausted_at >= deadline
        assert (
            parent.completed_at is None
            and parent.kratos_sessions is IdentityRecoveryCleanupState.PENDING
        )
        exhausted_at = parent.queue_exhausted_at
        assert child.status == JobStatus.FAILED.value and child.reason == "queue_wait_exhausted"
        assert child.terminal_at == exhausted_at
        assert (
            child.attempt_count == 0
            and child.work_deadline is None
            and child.pending_effect is None
        )
        assert await session.get(DurableJobAttemptRow, (binding.job_id.value, 1)) is None
        await session.delete(child)
    async with database.session() as session, session.begin():
        assert await _claim_private(session, binding, uuid4()) is None
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        reservation = await session.get(IdempotencyReservationRow, binding.operation_id.value)
        assert parent is not None and parent.queue_exhausted_at == exhausted_at
        assert parent.completed_at is None
        assert reservation is not None and reservation.expires_at is None


@pytest.mark.asyncio
async def test_suspension_claim_rereads_current_target_after_identity_wait(
    database: Database,
) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))

    async def claim() -> JobAttemptContextDTO | None:
        async with database.session() as session, session.begin():
            return await _claim_private(session, binding, uuid4())

    async with asyncio.TaskGroup() as tasks, database.session() as holder, holder.begin():
        await PostgresIdentityCoordinator(holder).acquire(
            installation_id=binding.installation_id, identity=binding.identity
        )
        target = await holder.get(PrincipalRow, binding.principal_id)
        assert target is not None and target.status is PrincipalStatus.SUSPENDED
        contender = tasks.create_task(claim())
        await wait_for_database_lock(database, contender)
        target.status = PrincipalStatus.ACTIVE

    assert contender.result() is None
    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        assert child is not None and child.status == JobStatus.FAILED.value
        assert child.reason == "original_suspension_not_current"
        assert child.attempt_count == 0 and child.fence is None and child.pending_effect is None


@pytest.mark.asyncio
async def test_private_claim_takes_the_oldest_due_suspension(database: Database) -> None:
    scope = await seed_membership_project(database)
    oldest = await _queued_suspension_binding(database, scope)
    newer = await _queued_suspension_binding(
        database, replace(scope, bob_id=scope.actor.access.actor_principal_id)
    )
    async with database.session() as session, session.begin():
        oldest_parent = await session.get(HumanSuspensionObligationRow, oldest.obligation_id.value)
        newer_parent = await session.get(HumanSuspensionObligationRow, newer.obligation_id.value)
        assert oldest_parent is not None and newer_parent is not None
        assert oldest_parent.admitted_at < newer_parent.admitted_at
        claimed = await _claim_private(session, oldest, uuid4())
        assert claimed is not None and claimed.job_id == oldest.job_id
    async with database.session() as session, session.begin():
        assert await _claim_private(session, newer, uuid4()) is None
        child = await session.get(DurableJobRow, newer.job_id.value)
        assert (
            child is not None
            and child.status == JobStatus.QUEUED.value
            and child.attempt_count == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["routine", "suspension"])
async def test_both_recovery_claim_paths_require_read_committed(
    database: Database, family: str
) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    operation_id = await _admit_routine_cleanup(database, binding)
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            if family == "routine":
                await _claim_routine(session, binding, operation_id)
            else:
                await _claim_private(session, binding, uuid4())
        await session.rollback()

    async with database.session() as session, session.begin():
        work = await _routine_reader(session, binding).lock_work(operation_id)
        child = await session.get(DurableJobRow, binding.job_id.value)
        assert work is not None and work.claim is None and work.run.consumed_attempts == 0
        assert child is not None and child.status == JobStatus.QUEUED.value
        assert child.attempt_count == 0 and child.work_deadline is None


@pytest.mark.asyncio
async def test_private_cleanup_stops_after_three_original_attempts(database: Database) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    original_deadline = None
    for ordinal in range(1, 4):
        async with database.session() as session, session.begin():
            claimed = await _claim_private(session, binding, uuid4())
            assert claimed is not None and claimed.attempt == ordinal
            if original_deadline is None:
                original_deadline = claimed.work_deadline
            assert claimed.work_deadline == original_deadline

        async with database.session() as session, session.begin():
            child = await session.get(DurableJobRow, binding.job_id.value)
            attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, ordinal))
            assert child is not None and attempt is not None and attempt.ended_at is None
            assert child.pending_effect is None and attempt.fence == claimed.fence.value
            child.lease_expires_at = attempt.started_at
        async with database.session() as session, session.begin():
            assert await _claim_private(session, binding, uuid4()) is None

        async with database.session() as session, session.begin():
            child = await session.get(DurableJobRow, binding.job_id.value)
            attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, ordinal))
            assert child is not None and attempt is not None and attempt.ended_at is not None
            assert child.attempt_count == ordinal and child.work_deadline == original_deadline
            if ordinal < 3:
                assert child.status == JobStatus.QUEUED.value
                now = await session.scalar(
                    select(func.clock_timestamp(type_=DateTime(timezone=True)))
                )
                assert now is not None
                child.due_at = now
            else:
                assert child.status == JobStatus.FAILED.value
                assert child.reason == attempt.reason == "attempt_budget_exhausted"
                assert child.terminal_at == attempt.ended_at

    async with database.session() as session, session.begin():
        assert await _claim_private(session, binding, uuid4()) is None
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        assert parent is not None and parent.completed_at is None
        assert await session.get(DurableJobAttemptRow, (binding.job_id.value, 4)) is None


@pytest.mark.asyncio
async def test_live_suspension_attempt_reads_current_original_authority(database: Database) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    async with database.session() as session, session.begin():
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        target = await session.get(PrincipalRow, binding.principal_id)
        row = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        assert parent is not None and parent.completed_at is None
        assert target is not None and target.status is PrincipalStatus.SUSPENDED
        assert row is not None and row.status == JobStatus.RUNNING.value
        assert attempt is not None and attempt.ended_at is None
        assert row.worker_id == attempt.worker_id == worker_id
        assert row.fence == attempt.fence == context.fence.value
        assert row.work_deadline == context.work_deadline and row.lease_expires_at is not None

        facts = await PostgresHumanSuspensionJobFactsReader(session).read_live_attempt(
            context, worker_id=worker_id
        )
        assert facts is not None
        assert (facts.binding, facts.payload) == (binding, context.payload)
        assert (facts.attempt, facts.fence, facts.worker_id) == (
            context.attempt,
            context.fence,
            worker_id,
        )
        assert facts.work_deadline == context.work_deadline
        assert facts.lease_expires_at == row.lease_expires_at
        assert attempt.started_at <= facts.observed_at < facts.lease_expires_at
        assert facts.source_revision == parent.source_revision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step", "marker_name"),
    [
        (HumanSuspensionCleanupStep.KRATOS_SESSIONS, "kratos_sessions"),
        (HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS, "hydra_cli_grants"),
        (HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS, "hydra_remembered_logins"),
    ],
)
async def test_suspension_checkpoint_commits_and_confirms_one_live_step(
    database: Database,
    step: HumanSuspensionCleanupStep,
    marker_name: str,
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    marker = f"{marker_name}:1:{context.fence.value}"
    pending = IdentityRecoveryCleanupState.PENDING
    confirmed = IdentityRecoveryCleanupState.CONFIRMED

    async with database.session() as session, session.begin():
        facts = await HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        ).require_current(context, worker_id=worker_id)
        assert facts.binding == binding and facts.attempt == context.attempt == 1
        child = await session.get(DurableJobRow, context.job_id.value)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        assert child is not None and child.pending_effect is None
        assert parent is not None and parent.completed_at is None
        assert (
            parent.kratos_sessions,
            parent.hydra_cli_grants,
            parent.hydra_remembered_logins,
        ) == (pending, pending, pending)

        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            context, worker_id=worker_id, step=step
        )

    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, context.job_id.value)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        assert child is not None and child.pending_effect == marker
        assert parent is not None
        assert (
            parent.kratos_sessions,
            parent.hydra_cli_grants,
            parent.hydra_remembered_logins,
        ) == (pending, pending, pending)

        await PostgresHumanSuspensionCleanupCheckpointWriter(session).confirm(
            context, worker_id=worker_id, step=step
        )

    async with database.session() as session:
        child = await session.get(DurableJobRow, context.job_id.value)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        assert child is not None and child.pending_effect is None
        assert child.status == JobStatus.RUNNING.value and child.fence == context.fence.value
        assert child.lease_expires_at == facts.lease_expires_at
        assert (
            child.work_deadline == context.work_deadline and child.checkpoint == context.checkpoint
        )
        assert parent is not None and parent.completed_at is None
        assert parent.source_revision == facts.source_revision
        assert (
            parent.kratos_sessions,
            parent.hydra_cli_grants,
            parent.hydra_remembered_logins,
        ) == (
            confirmed if step is HumanSuspensionCleanupStep.KRATOS_SESSIONS else pending,
            confirmed if step is HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS else pending,
            confirmed if step is HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS else pending,
        )

    async with database.session() as session, session.begin():
        with pytest.raises(ConflictError):
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                context, worker_id=worker_id, step=step
            )
        child = await session.get(DurableJobRow, context.job_id.value)
        assert child is not None and child.pending_effect is None


async def _host_cleanup(
    database: Database, command: HumanSuspensionCleanupMaintenanceCommand
) -> HumanSuspensionCleanupMaintenanceResultDTO:
    async with database.session() as session:
        return await HumanSuspensionCleanupMaintenanceService(
            SqlAlchemyRecoveryTransactionManager(session),
            PostgresHumanSuspensionCleanupMaintenanceRepository(session),
        ).execute(command=command)


async def _expire_cleanup_lease(database: Database, context: JobAttemptContextDTO) -> None:
    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        assert child is not None and attempt is not None
        child.lease_expires_at = attempt.started_at


async def _stop_suspension_with_marker(
    database: Database, *, outcome: IdentityRecoveryCleanupState | None = None
) -> tuple[HumanSuspensionJobBindingDTO, JobAttemptContextDTO]:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    worker_id = uuid4()
    async with database.session() as session, session.begin():
        first = await _claim_private(session, binding, worker_id)
        assert first is not None

    await _commit_cleanup_step(
        database, first, worker_id, HumanSuspensionCleanupStep.KRATOS_SESSIONS
    )
    step = HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            first, worker_id=worker_id, step=step
        )
    if outcome is not None:
        async with database.session() as session, session.begin():
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).record_nonconfirmation(
                first, worker_id=worker_id, step=step, outcome=outcome
            )
    await _expire_cleanup_lease(database, first)
    async with database.session() as session, session.begin():
        assert await _claim_private(session, binding, uuid4()) is None

    return binding, first


def _continue_command(
    binding: HumanSuspensionJobBindingDTO,
) -> HumanSuspensionCleanupMaintenanceCommand:
    return HumanSuspensionCleanupMaintenanceCommand(
        expected_installation_id=binding.installation_id,
        operation_id=OperationId("continue-stopped-suspension"),
        cleanup_operation_id=OperationId(str(binding.obligation_id.value)),
        intent=HumanSuspensionCleanupMaintenanceIntent.CONTINUE,
        operator_label="Operator",
        reason="Authorize one repeat of the uncertain step",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interruption", [None, "before_commit", "after_commit"], ids=["normal", "rollback", "lost-ack"]
)
async def test_host_continues_exact_stopped_suspension_and_replays_its_original(
    database: Database,
    interruption: str | None,
) -> None:
    binding, first = await _stop_suspension_with_marker(database)
    step = HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS
    marker = f"{step.value}:{first.attempt}:{first.fence.value}"
    command = _continue_command(binding)
    receipt_key = binding.installation_id.value, command.operation_id.value
    inspect = replace(
        command,
        intent=HumanSuspensionCleanupMaintenanceIntent.INSPECT,
        operator_label=None,
        reason=None,
    )
    status = await _host_cleanup(database, inspect)
    assert status.outcome is HumanSuspensionCleanupExecutionState.STOPPED
    assert status.kratos_sessions is IdentityRecoveryCleanupState.CONFIRMED
    assert status.hydra_cli_grants is IdentityRecoveryCleanupState.UNCERTAIN
    assert status.hydra_remembered_logins is IdentityRecoveryCleanupState.PENDING
    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, first.attempt))
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert child is not None and parent is not None and attempt is not None and now is not None
        assert child.status == JobStatus.RECOVERY_REQUIRED.value
        assert child.pending_effect == marker and child.attempt_count == first.attempt
        assert child.worker_id is None and child.fence is None and child.lease_expires_at is None
        assert child.queued_deadline > now and first.work_deadline > now
        assert attempt.ended_at is not None and attempt.fence == first.fence.value
        assert parent.kratos_sessions is IdentityRecoveryCleanupState.CONFIRMED
        assert parent.hydra_cli_grants is IdentityRecoveryCleanupState.PENDING
        assert parent.completed_at is None and parent.queue_exhausted_at is None
        assert await session.get(HostMaintenanceReceiptRow, receipt_key) is None
        original_bounds = child.admitted_at, child.queued_deadline, child.work_deadline
        original_payload = child.payload
        ended_at = attempt.ended_at

    if interruption is not None:
        async with database.session() as session:

            def interrupt(_session: Session) -> None:
                raise OperationalError("commit acknowledgment", None, ConnectionError("private"))

            event.listen(session.sync_session, interruption, interrupt, once=True)
            with pytest.raises(DependencyUnavailableError):
                await HumanSuspensionCleanupMaintenanceService(
                    SqlAlchemyRecoveryTransactionManager(session),
                    PostgresHumanSuspensionCleanupMaintenanceRepository(session),
                ).execute(command=command)
        async with database.session() as session:
            child = await session.get(DurableJobRow, binding.job_id.value)
            assert child is not None
            if interruption == "after_commit":
                assert child.status == JobStatus.QUEUED.value
                assert await session.get(HostMaintenanceReceiptRow, receipt_key) is not None
            else:
                assert child.status == JobStatus.RECOVERY_REQUIRED.value
                assert await session.get(HostMaintenanceReceiptRow, receipt_key) is None

    result = await _host_cleanup(database, command)
    assert result.operation_id == command.operation_id
    assert result.installation_id == binding.installation_id
    assert result.cleanup_operation_id == command.cleanup_operation_id
    assert result.outcome is HumanSuspensionCleanupContinueOutcome.REQUEUED

    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        receipt = await session.get(HostMaintenanceReceiptRow, receipt_key)
        assert child is not None and receipt is not None
        assert child.status == JobStatus.QUEUED.value and child.terminal_at is None
        assert child.pending_effect == marker and child.attempt_count == first.attempt
        assert child.payload == original_payload
        assert (child.admitted_at, child.queued_deadline, child.work_deadline) == original_bounds
        assert receipt.mode == "human-suspension-cleanup" and receipt.outcome == "requeued"
        assert receipt.operator_label == command.operator_label and receipt.reason == command.reason
        assert receipt.suspension_obligation_id == binding.obligation_id.value
        assert (
            receipt.suspension_repeat_step,
            receipt.suspension_repeat_attempt,
            receipt.suspension_repeat_fence,
            receipt.suspension_repeat_consumed_at,
        ) == (step.value, first.attempt, first.fence.value, None)
        requeued_due_at = child.due_at
        authorized_at = receipt.authorized_at

    assert await _host_cleanup(database, command) == result
    queued = await _host_cleanup(database, inspect)
    assert queued.outcome is HumanSuspensionCleanupExecutionState.QUEUED
    assert queued.kratos_sessions is IdentityRecoveryCleanupState.CONFIRMED
    assert queued.hydra_cli_grants is IdentityRecoveryCleanupState.UNCERTAIN
    assert queued.hydra_remembered_logins is IdentityRecoveryCleanupState.PENDING
    for different in (
        replace(command, cleanup_operation_id=OperationId(str(uuid4()))),
        replace(command, reason="Different reason"),
        replace(command, operator_label="Different operator"),
    ):
        with pytest.raises(HumanSuspensionCleanupMaintenanceError) as rejected:
            await _host_cleanup(database, different)
        assert rejected.value.code is HumanSuspensionCleanupMaintenanceErrorCode.KEY_REUSED

    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, first.attempt))
        receipt = await session.get(HostMaintenanceReceiptRow, receipt_key)
        assert child is not None and attempt is not None and receipt is not None
        assert child.status == JobStatus.QUEUED.value and child.due_at == requeued_due_at
        assert child.pending_effect == marker and child.attempt_count == first.attempt
        assert receipt.suspension_repeat_consumed_at is None
        assert attempt.ended_at == ended_at and attempt.fence == first.fence.value
        assert receipt.authorized_at == authorized_at
        assert (
            await session.get(DurableJobAttemptRow, (binding.job_id.value, first.attempt + 1))
            is None
        )
        with pytest.raises(RecoveryMaintenanceError) as rejected:
            await PostgresIdentityRecoveryCleanupResumeFactsReader(session).receipt(
                installation_id=binding.installation_id, operation_id=command.operation_id
            )
        assert rejected.value.code is RecoveryMaintenanceErrorCode.KEY_REUSED


@pytest.mark.asyncio
async def test_host_continue_serializes_repeat_authority_across_request_keys(
    database: Database,
) -> None:
    binding, _ = await _stop_suspension_with_marker(database)
    first = _continue_command(binding)
    second = replace(first, operation_id=OperationId("another-operator-request"))
    async with asyncio.TaskGroup() as tasks:
        operations = [tasks.create_task(_host_cleanup(database, c)) for c in (first, second, first)]
    results = [t.result() for t in operations]
    assert results[0] == results[2]
    assert {results[0].outcome, results[1].outcome} == {
        HumanSuspensionCleanupContinueOutcome.REQUEUED,
        HumanSuspensionCleanupContinueOutcome.ALREADY_SCHEDULED,
    }
    async with database.session() as session:
        receipts = (
            await session.scalars(
                select(HostMaintenanceReceiptRow).where(
                    HostMaintenanceReceiptRow.suspension_obligation_id
                    == binding.obligation_id.value
                )
            )
        ).all()
        assert (
            len(receipts) == 2 and sum(r.suspension_repeat_step is not None for r in receipts) == 1
        )


@pytest.mark.asyncio
async def test_installed_host_command_inspects_and_continues_without_provider_settings(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    binding, _ = await _stop_suspension_with_marker(database)
    common: dict[str, object] = {
        "schemaVersion": 1,
        "mode": "human-suspension-cleanup",
        "operationId": "installed-host-continue",
        "cleanupOperationId": str(binding.obligation_id.value),
    }
    target = {"expectedInstallationId": str(binding.installation_id.value)}
    response = common | {"installationId": target["expectedInstallationId"]}
    inspected = await run_maintenance(
        common | target | {"intent": "inspect"}, temporary_postgres_settings
    )
    assert inspected == (
        0,
        response
        | {
            "intent": "inspect",
            "execution": "stopped",
            "steps": {
                "kratosSessions": "confirmed",
                "hydraCliGrants": "uncertain",
                "hydraRememberedLogins": "pending",
            },
        },
    ), "The installed inspector must report the stopped marker as uncertain."
    request = (
        common
        | target
        | {"intent": "continue", "operatorLabel": "Operator", "reason": "Continue exact original"}
    )
    expected = 0, response | {"intent": "continue", "outcome": "requeued"}
    assert await run_maintenance(request, temporary_postgres_settings) == expected
    assert await run_maintenance(request, temporary_postgres_settings) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved_outcome",
    [None, IdentityRecoveryCleanupState.FAILED, IdentityRecoveryCleanupState.UNCERTAIN],
    ids=["pending", "failed", "uncertain"],
)
async def test_host_inspects_unresolved_marker_while_attempt_is_live(
    database: Database, saved_outcome: IdentityRecoveryCleanupState | None
) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    worker = uuid4()
    async with database.session() as session, session.begin():
        live = await _claim_private(session, binding, worker)
        assert live is not None

    await _commit_cleanup_step(database, live, worker, HumanSuspensionCleanupStep.KRATOS_SESSIONS)
    step = HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            live, worker_id=worker, step=step
        )
    if saved_outcome is not None:
        async with database.session() as session, session.begin():
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).record_nonconfirmation(
                live, worker_id=worker, step=step, outcome=saved_outcome
            )

    inspect = replace(
        _continue_command(binding),
        intent=HumanSuspensionCleanupMaintenanceIntent.INSPECT,
        operator_label=None,
        reason=None,
    )
    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        assert child is not None and child.lease_expires_at is not None
        lease = child.lease_expires_at

    observed = await _host_cleanup(database, inspect)

    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, live.attempt))
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert child is not None and parent is not None and attempt is not None and now is not None
        assert child.status == JobStatus.RUNNING.value and now < lease
        assert child.pending_effect == f"{step.value}:{live.attempt}:{live.fence.value}"
        assert (child.attempt_count, child.fence, child.worker_id, child.lease_expires_at) == (
            live.attempt,
            live.fence.value,
            worker,
            lease,
        )
        assert attempt.ended_at is None and parent.completed_at is None
        assert parent.hydra_cli_grants is (saved_outcome or IdentityRecoveryCleanupState.PENDING)
        assert (
            await session.get(
                HostMaintenanceReceiptRow,
                (binding.installation_id.value, inspect.operation_id.value),
            )
            is None
        )
    assert observed.outcome is HumanSuspensionCleanupExecutionState.RUNNING
    assert observed.kratos_sessions is IdentityRecoveryCleanupState.CONFIRMED
    assert observed.hydra_remembered_logins is IdentityRecoveryCleanupState.PENDING
    assert observed.hydra_cli_grants is (saved_outcome or IdentityRecoveryCleanupState.UNCERTAIN), (
        "The live marker must report uncertainty until a fenced result is saved."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    ["foreign-installation", "missing", "canceled", "exhausted", "wrong-fence", "other-mode"],
)
async def test_host_continue_rejects_unavailable_authority_without_a_receipt(
    database: Database,
    scenario: str,
) -> None:
    binding, first = await _stop_suspension_with_marker(database)
    command = _continue_command(binding)
    code = HumanSuspensionCleanupMaintenanceErrorCode.NOT_CONTINUABLE
    receipt_key = binding.installation_id.value, command.operation_id.value
    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, binding.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (binding.job_id.value, first.attempt))
        assert child is not None and attempt is not None and attempt.ended_at is not None
        match scenario:
            case "foreign-installation":
                command = replace(command, expected_installation_id=InstallationId(uuid4()))
                code = HumanSuspensionCleanupMaintenanceErrorCode.INSTALLATION_MISMATCH
            case "missing":
                command = replace(command, cleanup_operation_id=OperationId(str(uuid4())))
                code = HumanSuspensionCleanupMaintenanceErrorCode.NOT_FOUND
            case "canceled":
                child.cancel_requested = True
            case "exhausted":
                child.work_deadline = attempt.ended_at
            case "wrong-fence":
                child.pending_effect = f"hydra_cli_grants:{first.attempt}:{uuid4()}"
            case "other-mode":
                session.add(
                    HostMaintenanceReceiptRow(
                        installation_id=binding.installation_id.value,
                        operator_request_id=command.operation_id.value,
                        authority=binding.identity.authority.value,
                        subject=binding.identity.subject.value,
                        mode="bootstrap-first-administrator",
                        outcome="bootstrapped",
                        recovery_operation_id=None,
                        released=None,
                        run_id=None,
                        deadline=None,
                        operator_label="Operator",
                        reason="Existing original",
                        authorized_at=attempt.ended_at,
                    )
                )
                code = HumanSuspensionCleanupMaintenanceErrorCode.KEY_REUSED
            case _:
                raise ValueError("Unsupported test scenario.")

    with pytest.raises(HumanSuspensionCleanupMaintenanceError) as denied:
        await _host_cleanup(database, command)
    assert denied.value.code is code
    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        receipt = await session.get(HostMaintenanceReceiptRow, receipt_key)
        assert child is not None and child.status == JobStatus.RECOVERY_REQUIRED.value
        assert child.attempt_count == first.attempt
        if scenario == "other-mode":
            assert receipt is not None and receipt.mode == "bootstrap-first-administrator"
            assert receipt.suspension_obligation_id is None
        else:
            assert receipt is None


@pytest.mark.asyncio
async def test_host_continue_keeps_current_scheduled_or_completed_work_as_is(
    database: Database,
) -> None:
    binding = await _queued_suspension_binding(database, await seed_membership_project(database))
    command = _continue_command(binding)
    queued = await _host_cleanup(database, command)
    assert queued.outcome is HumanSuspensionCleanupContinueOutcome.ALREADY_SCHEDULED
    worker = uuid4()
    async with database.session() as session, session.begin():
        live = await _claim_private(session, binding, worker)
        assert live is not None and live.attempt == 1
    running = await _host_cleanup(database, replace(command, operation_id=OperationId("running")))
    assert running.outcome is HumanSuspensionCleanupContinueOutcome.ALREADY_SCHEDULED
    for step in HumanSuspensionCleanupStep:
        await _commit_cleanup_step(database, live, worker, step)
    complete = await _host_cleanup(database, replace(command, operation_id=OperationId("complete")))
    assert complete.outcome is HumanSuspensionCleanupContinueOutcome.ALREADY_COMPLETE
    assert await _host_cleanup(database, command) == queued
    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        assert child is not None and child.status == JobStatus.SUCCEEDED.value
        assert child.attempt_count == 1 and child.work_deadline == live.work_deadline
        assert not await session.scalar(
            select(func.count())
            .select_from(HostMaintenanceReceiptRow)
            .where(
                HostMaintenanceReceiptRow.suspension_obligation_id == binding.obligation_id.value,
                HostMaintenanceReceiptRow.suspension_repeat_step.is_not(None),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [False, True], ids=["lost-marker-ack", "pre-marker-crash"])
async def test_host_repeat_is_consumed_only_by_the_next_committed_exact_marker(
    database: Database,
    replacement: bool,
) -> None:
    binding, first = await _stop_suspension_with_marker(
        database, outcome=IdentityRecoveryCleanupState.FAILED
    )
    command = _continue_command(binding)
    assert (
        await _host_cleanup(database, command)
    ).outcome is HumanSuspensionCleanupContinueOutcome.REQUEUED
    receipt_key = binding.installation_id.value, command.operation_id.value
    worker = uuid4()
    async with database.session() as session, session.begin():
        repeat = await _claim_private(session, binding, worker)
        assert repeat is not None and repeat.attempt == 2 and repeat.fence != first.fence
        assert repeat.work_deadline == first.work_deadline
    step = HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS
    marker = f"{step.value}:{first.attempt}:{first.fence.value}"
    async with database.session() as session, session.begin() as transaction:
        checkpoints = PostgresHumanSuspensionCleanupCheckpointWriter(session)
        with pytest.raises(ConflictError):
            await checkpoints.begin(
                repeat, worker_id=worker, step=HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS
            )
        await checkpoints.begin(repeat, worker_id=worker, step=step)
        await transaction.rollback()

    if replacement:
        await _expire_cleanup_lease(database, repeat)
        async with database.session() as session, session.begin():
            assert await _claim_private(session, binding, uuid4()) is None
        async with database.session() as session, session.begin():
            child = await session.get(DurableJobRow, binding.job_id.value)
            previous = await session.get(
                DurableJobAttemptRow, (binding.job_id.value, repeat.attempt)
            )
            assert child is not None and previous is not None and previous.ended_at is not None
            assert child.status == JobStatus.QUEUED.value
            assert child.due_at == previous.ended_at + timedelta(seconds=10)
            assert child.pending_effect == marker and child.work_deadline == first.work_deadline
            child.due_at = previous.ended_at
        next_worker = uuid4()
        async with database.session() as session, session.begin():
            next_attempt = await _claim_private(session, binding, next_worker)
            assert next_attempt is not None and next_attempt.attempt == 3
            assert (
                next_attempt.fence != repeat.fence
                and next_attempt.work_deadline == first.work_deadline
            )
            with pytest.raises(AccessDeniedError):
                await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                    repeat, worker_id=worker, step=step
                )
        repeat, worker = next_attempt, next_worker

    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        receipt = await session.get(HostMaintenanceReceiptRow, receipt_key)
        assert child is not None and parent is not None and receipt is not None
        assert child.pending_effect == marker and receipt.suspension_repeat_consumed_at is None
        assert parent.hydra_cli_grants is IdentityRecoveryCleanupState.FAILED

    if replacement:
        async with database.session() as session, session.begin():
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                repeat, worker_id=worker, step=step
            )
        async with database.session() as session, session.begin():
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).confirm(
                repeat, worker_id=worker, step=step
            )
    else:
        async with database.session() as session:

            def lose_ack(_session: Session) -> None:
                raise OperationalError("marker acknowledgment", None, ConnectionError("private"))

            event.listen(session.sync_session, "after_commit", lose_ack, once=True)
            with pytest.raises(DependencyUnavailableError):
                async with SqlAlchemyRecoveryTransactionManager(session).begin():
                    await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                        repeat, worker_id=worker, step=step
                    )
        async with database.session() as session, session.begin():
            with pytest.raises(ConflictError):
                await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                    repeat, worker_id=worker, step=step
                )

    async with database.session() as session:
        child = await session.get(DurableJobRow, binding.job_id.value)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        receipt = await session.get(HostMaintenanceReceiptRow, receipt_key)
        earlier = await session.get(DurableJobAttemptRow, (binding.job_id.value, first.attempt))
        assert (
            child is not None and parent is not None and receipt is not None and earlier is not None
        )
        assert receipt.suspension_repeat_consumed_at is not None
        assert earlier.reason == "suspension_repeat:hydra_cli_grants:failed"
        assert parent.kratos_sessions is IdentityRecoveryCleanupState.CONFIRMED
        assert parent.hydra_remembered_logins is IdentityRecoveryCleanupState.PENDING
        if replacement:
            assert child.pending_effect is None
            assert parent.hydra_cli_grants is IdentityRecoveryCleanupState.CONFIRMED
        else:
            assert child.pending_effect == f"{step.value}:{repeat.attempt}:{repeat.fence.value}"
            assert parent.hydra_cli_grants is IdentityRecoveryCleanupState.PENDING
    await _expire_cleanup_lease(database, repeat)
    async with database.session() as session, session.begin():
        assert await _claim_private(session, binding, uuid4()) is None
    assert (
        await _host_cleanup(database, command)
    ).outcome is HumanSuspensionCleanupContinueOutcome.REQUEUED
    with pytest.raises(HumanSuspensionCleanupMaintenanceError) as denied:
        await _host_cleanup(database, replace(command, operation_id=OperationId("another-repeat")))
    assert denied.value.code is HumanSuspensionCleanupMaintenanceErrorCode.NOT_CONTINUABLE


async def _commit_cleanup_step(
    database: Database,
    context: JobAttemptContextDTO,
    worker_id: UUID,
    step: HumanSuspensionCleanupStep,
) -> None:
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            context, worker_id=worker_id, step=step
        )
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).confirm(
            context, worker_id=worker_id, step=step
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", [IdentityRecoveryCleanupState.FAILED, IdentityRecoveryCleanupState.UNCERTAIN]
)
async def test_suspension_checkpoint_retains_nonconfirmation_and_its_marker(
    database: Database, outcome: IdentityRecoveryCleanupState
) -> None:
    scope = await seed_membership_project(database)
    context, worker_id = await _live_suspension_attempt(database, scope=scope)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    await _commit_cleanup_step(
        database, context, worker_id, HumanSuspensionCleanupStep.KRATOS_SESSIONS
    )

    step = HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS
    marker = f"hydra_cli_grants:{context.attempt}:{context.fence.value}"
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            context, worker_id=worker_id, step=step
        )

    async with database.session() as session, session.begin():
        facts = await HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        ).require_current(context, worker_id=worker_id)
        child = await session.get(DurableJobRow, context.job_id.value)
        reservation = await session.get(IdempotencyReservationRow, binding.operation_id.value)
        assert facts.binding == binding
        assert child is not None and child.pending_effect == marker
        assert reservation is not None
        schedule = child.admitted_at, child.queued_deadline, child.due_at
        retention = reservation.state, reservation.replay_kind, reservation.expires_at

        await PostgresHumanSuspensionCleanupCheckpointWriter(session).record_nonconfirmation(
            context, worker_id=worker_id, step=step, outcome=outcome
        )

    async with database.session() as session, session.begin():
        writer = PostgresHumanSuspensionCleanupCheckpointWriter(session)
        conflicting = (
            IdentityRecoveryCleanupState.FAILED
            if outcome is IdentityRecoveryCleanupState.UNCERTAIN
            else IdentityRecoveryCleanupState.UNCERTAIN
        )
        with pytest.raises(ConflictError):
            await writer.record_nonconfirmation(
                context, worker_id=worker_id, step=step, outcome=conflicting
            )
        with pytest.raises(ConflictError):
            await writer.confirm(context, worker_id=worker_id, step=step)

    async with database.session() as session, session.begin():
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        child = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        assert parent is not None and child is not None and attempt is not None
        assert parent.kratos_sessions is IdentityRecoveryCleanupState.CONFIRMED
        assert parent.hydra_cli_grants is outcome
        assert parent.hydra_remembered_logins is IdentityRecoveryCleanupState.PENDING
        assert parent.completed_at is None and parent.queue_exhausted_at is None
        assert child.pending_effect == marker
        assert child.status == JobStatus.RUNNING.value and child.terminal_at is None
        assert child.worker_id == attempt.worker_id == worker_id
        assert child.fence == attempt.fence == context.fence.value
        assert child.lease_expires_at == facts.lease_expires_at
        assert (
            child.work_deadline == context.work_deadline and child.checkpoint == context.checkpoint
        )
        assert (child.admitted_at, child.queued_deadline, child.due_at) == schedule
        assert (parent.admitted_at, parent.queued_deadline) == schedule[:2]
        reservation = await session.get(IdempotencyReservationRow, binding.operation_id.value)
        assert reservation is not None
        assert (reservation.state, reservation.replay_kind, reservation.expires_at) == retention
        assert attempt.ended_at is None

        restoration = await PostgresHumanLifecycleFactsReader(session).read_authorization(
            access=scope.actor.access,
            organization_id=scope.actor.organization_id,
            principal_id=scope.bob_id,
            action_id=ActionId(OrganizationAction.RESTORE_USERS.value),
        )
        assert restoration is not None and restoration.actor_has_action
        assert (
            restoration.target is not None
            and restoration.target.status is PrincipalStatus.SUSPENDED
        )
        assert restoration.current_suspension is not None
        assert restoration.current_suspension.id == binding.obligation_id
        assert not restoration.required_cleanup_confirmed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "outcome", "error"),
    [
        pytest.param(
            "missing", IdentityRecoveryCleanupState.UNCERTAIN, ConflictError, id="missing-marker"
        ),
        pytest.param(
            "wrong", IdentityRecoveryCleanupState.FAILED, ConflictError, id="wrong-step-marker"
        ),
        pytest.param(
            "stale", IdentityRecoveryCleanupState.UNCERTAIN, AccessDeniedError, id="stale-fence"
        ),
        pytest.param("invalid", IdentityRecoveryCleanupState.PENDING, ValueError, id="pending"),
        pytest.param("invalid", IdentityRecoveryCleanupState.CONFIRMED, ValueError, id="confirmed"),
        pytest.param("rollback", IdentityRecoveryCleanupState.FAILED, None, id="rollback"),
    ],
)
async def test_suspension_nonconfirmation_preserves_the_original_on_rejection_or_rollback(
    database: Database,
    case: str,
    outcome: IdentityRecoveryCleanupState,
    error: type[Exception] | None,
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    step = HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS
    marked_step = HumanSuspensionCleanupStep.KRATOS_SESSIONS if case == "wrong" else step
    marker = None
    if case != "missing":
        async with database.session() as session, session.begin():
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                context, worker_id=worker_id, step=marked_step
            )
        marker = f"{marked_step.value}:{context.attempt}:{context.fence.value}"

    async with database.session() as session, session.begin() as transaction:
        child = await session.get(DurableJobRow, context.job_id.value)
        assert child is not None and child.pending_effect == marker
        assert child.lease_expires_at is not None
        lease_expires_at = child.lease_expires_at
        submitted = replace(context, fence=JobFence(uuid4())) if case == "stale" else context
        writer = PostgresHumanSuspensionCleanupCheckpointWriter(session)
        if error is None:
            await writer.record_nonconfirmation(
                submitted, worker_id=worker_id, step=step, outcome=outcome
            )
            parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
            assert parent is not None and parent.hydra_cli_grants is outcome
            await transaction.rollback()
        else:
            with pytest.raises(error):
                await writer.record_nonconfirmation(
                    submitted, worker_id=worker_id, step=step, outcome=outcome
                )

    async with database.session() as session:
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        child = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        assert parent is not None and child is not None and attempt is not None
        assert (
            parent.kratos_sessions,
            parent.hydra_cli_grants,
            parent.hydra_remembered_logins,
        ) == (IdentityRecoveryCleanupState.PENDING,) * 3
        assert parent.completed_at is None and parent.queue_exhausted_at is None
        assert child.pending_effect == marker
        assert child.status == JobStatus.RUNNING.value and child.terminal_at is None
        assert child.worker_id == attempt.worker_id == worker_id
        assert child.fence == attempt.fence == context.fence.value
        assert (
            child.lease_expires_at == lease_expires_at
            and child.work_deadline == context.work_deadline
        )
        assert attempt.ended_at is None


@pytest.mark.asyncio
async def test_final_suspension_checkpoint_completes_original_and_retires_attempt(
    database: Database,
) -> None:
    scope = await seed_membership_project(database)
    context, worker_id = await _live_suspension_attempt(database, scope=scope)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    restore_action = ActionId(OrganizationAction.RESTORE_USERS.value)
    steps = (
        HumanSuspensionCleanupStep.KRATOS_SESSIONS,
        HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS,
        HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS,
    )
    async with database.session() as session:
        child = await session.get(DurableJobRow, context.job_id.value)
        reservation = await session.get(IdempotencyReservationRow, binding.operation_id.value)
        assert child is not None and reservation is not None
        original_schedule = child.admitted_at, child.queued_deadline, child.due_at
        original_retention = reservation.state, reservation.replay_kind, reservation.expires_at

    completed_at = None
    for count, step in enumerate(steps, start=1):
        await _commit_cleanup_step(database, context, worker_id, step)

        async with database.session() as session, session.begin():
            parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
            child = await session.get(DurableJobRow, context.job_id.value)
            attempt = await session.get(
                DurableJobAttemptRow, (context.job_id.value, context.attempt)
            )
            assert parent is not None and child is not None and attempt is not None
            assert child.pending_effect is None
            assert child.attempt_count == attempt.number == context.attempt
            assert child.work_deadline == context.work_deadline
            assert attempt.worker_id == worker_id and attempt.fence == context.fence.value
            assert parent.operation_id == binding.operation_id.value
            assert (
                parent.kratos_sessions,
                parent.hydra_cli_grants,
                parent.hydra_remembered_logins,
            ) == (IdentityRecoveryCleanupState.CONFIRMED,) * count + (
                IdentityRecoveryCleanupState.PENDING,
            ) * (len(steps) - count)

            facts = await PostgresHumanLifecycleFactsReader(session).read_authorization(
                access=scope.actor.access,
                organization_id=scope.actor.organization_id,
                principal_id=scope.bob_id,
                action_id=restore_action,
            )
            assert facts is not None and facts.actor_has_action
            assert facts.target is not None and facts.target.status is PrincipalStatus.SUSPENDED
            assert facts.current_suspension is not None
            assert facts.current_suspension.id == binding.obligation_id
            assert facts.access_revision == binding.access_revision

            if count < len(steps):
                assert parent.completed_at is None and not facts.required_cleanup_confirmed
                assert child.status == JobStatus.RUNNING.value and child.terminal_at is None
                assert child.worker_id == worker_id and child.fence == context.fence.value
                assert child.lease_expires_at is not None and attempt.ended_at is None
            else:
                assert parent.completed_at is not None, (
                    "The final live confirmation must complete its original."
                )
                completed_at = parent.completed_at
                assert child.status == JobStatus.SUCCEEDED.value
                assert parent.completed_at == child.terminal_at == attempt.ended_at
                assert attempt.started_at <= parent.completed_at < context.work_deadline
                assert child.worker_id is None and child.fence is None
                assert child.lease_expires_at is None
                assert child.reason is None and attempt.reason is None
                assert facts.required_cleanup_confirmed and not facts.has_newer_recovery_block

    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).confirm(
                context, worker_id=worker_id, step=steps[-1]
            )

    async with database.session() as session:
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        child = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        reservation = await session.get(IdempotencyReservationRow, binding.operation_id.value)
        assert parent is not None and child is not None and attempt is not None
        assert completed_at is not None
        assert parent.completed_at == child.terminal_at == attempt.ended_at == completed_at
        assert child.status == JobStatus.SUCCEEDED.value and child.pending_effect is None
        assert (child.admitted_at, child.queued_deadline, child.due_at) == original_schedule
        assert (parent.admitted_at, parent.queued_deadline) == original_schedule[:2]
        assert reservation is not None
        assert (reservation.state, reservation.replay_kind, reservation.expires_at) == (
            original_retention
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["rollback", "expired-lease"])
async def test_final_suspension_checkpoint_preserves_unfinished_work_after_interruption(
    database: Database, interruption: str
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    confirmed = IdentityRecoveryCleanupState.CONFIRMED
    pending = IdentityRecoveryCleanupState.PENDING
    for step in (
        HumanSuspensionCleanupStep.KRATOS_SESSIONS,
        HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS,
    ):
        await _commit_cleanup_step(database, context, worker_id, step)

    final_step = HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            context, worker_id=worker_id, step=final_step
        )
    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, context.job_id.value)
        assert child is not None and child.lease_expires_at is not None
        if interruption == "expired-lease":
            now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
            assert now is not None
            child.lease_expires_at = now - timedelta(seconds=1)
        lease_expires_at = child.lease_expires_at

    async with database.session() as session, session.begin() as transaction:
        writer = PostgresHumanSuspensionCleanupCheckpointWriter(session)
        if interruption == "rollback":
            await writer.confirm(context, worker_id=worker_id, step=final_step)
            await transaction.rollback()
        else:
            with pytest.raises(AccessDeniedError):
                await writer.confirm(context, worker_id=worker_id, step=final_step)

    async with database.session() as session:
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        child = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        target = await session.get(PrincipalRow, binding.principal_id)
        assert parent is not None and child is not None and attempt is not None
        assert parent.completed_at is None
        assert (
            parent.kratos_sessions,
            parent.hydra_cli_grants,
            parent.hydra_remembered_logins,
        ) == (confirmed, confirmed, pending)
        assert child.pending_effect == f"hydra_remembered_logins:1:{context.fence.value}"
        assert child.status == JobStatus.RUNNING.value and child.terminal_at is None
        assert child.worker_id == attempt.worker_id == worker_id
        assert child.fence == attempt.fence == context.fence.value
        assert child.lease_expires_at == lease_expires_at
        assert child.work_deadline == context.work_deadline
        assert attempt.ended_at is None and attempt.reason is None
        assert target is not None and target.status is PrincipalStatus.SUSPENDED


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback", ["begin", "confirm"])
async def test_suspension_checkpoint_rollback_preserves_the_original(
    database: Database, rollback: str
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    step = HumanSuspensionCleanupStep.KRATOS_SESSIONS
    marker = f"kratos_sessions:1:{context.fence.value}"
    async with database.session() as session, session.begin() as transaction:
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            context, worker_id=worker_id, step=step
        )
        if rollback == "begin":
            await transaction.rollback()
    if rollback == "confirm":
        async with database.session() as session, session.begin() as transaction:
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).confirm(
                context, worker_id=worker_id, step=step
            )
            await transaction.rollback()

    async with database.session() as session:
        child = await session.get(DurableJobRow, context.job_id.value)
        parent = await session.get(
            HumanSuspensionObligationRow, context.binding.obligation_id.value
        )
        assert child is not None and child.pending_effect == (
            marker if rollback == "confirm" else None
        )
        assert parent is not None and parent.kratos_sessions is IdentityRecoveryCleanupState.PENDING
        assert parent.completed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "step"),
    [
        ("begin", HumanSuspensionCleanupStep.KRATOS_SESSIONS),
        ("begin", HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS),
        ("confirm", HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS),
    ],
)
async def test_suspension_checkpoint_keeps_an_existing_marker(
    database: Database, operation: str, step: HumanSuspensionCleanupStep
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            context, worker_id=worker_id, step=HumanSuspensionCleanupStep.KRATOS_SESSIONS
        )

    async with database.session() as session, session.begin():
        writer = PostgresHumanSuspensionCleanupCheckpointWriter(session)
        with pytest.raises(ConflictError):
            if operation == "begin":
                await writer.begin(context, worker_id=worker_id, step=step)
            else:
                await writer.confirm(context, worker_id=worker_id, step=step)

    async with database.session() as session:
        child = await session.get(DurableJobRow, context.job_id.value)
        parent = await session.get(
            HumanSuspensionObligationRow, context.binding.obligation_id.value
        )
        assert (
            child is not None and child.pending_effect == f"kratos_sessions:1:{context.fence.value}"
        )
        assert parent is not None and parent.kratos_sessions is IdentityRecoveryCleanupState.PENDING
        assert parent.hydra_cli_grants is IdentityRecoveryCleanupState.PENDING


@pytest.mark.asyncio
async def test_suspension_checkpoint_rejects_a_noncurrent_fence_before_begin(
    database: Database,
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    crossed = replace(context, fence=JobFence(uuid4()))
    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
                crossed, worker_id=worker_id, step=HumanSuspensionCleanupStep.KRATOS_SESSIONS
            )

    async with database.session() as session:
        child = await session.get(DurableJobRow, context.job_id.value)
        assert (
            child is not None
            and child.pending_effect is None
            and child.fence == context.fence.value
        )


@pytest.mark.asyncio
async def test_suspension_checkpoint_rechecks_ownership_before_confirming_matching_marker(
    database: Database,
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    step = HumanSuspensionCleanupStep.KRATOS_SESSIONS
    async with database.session() as session, session.begin():
        await PostgresHumanSuspensionCleanupCheckpointWriter(session).begin(
            context, worker_id=worker_id, step=step
        )
    async with database.session() as session, session.begin():
        child = await session.get(DurableJobRow, context.job_id.value)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert child is not None and now is not None
        child.lease_expires_at = now - timedelta(seconds=1)

    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await PostgresHumanSuspensionCleanupCheckpointWriter(session).confirm(
                context, worker_id=worker_id, step=step
            )

    async with database.session() as session:
        child = await session.get(DurableJobRow, context.job_id.value)
        parent = await session.get(
            HumanSuspensionObligationRow, context.binding.obligation_id.value
        )
        assert (
            child is not None and child.pending_effect == f"kratos_sessions:1:{context.fence.value}"
        )
        assert parent is not None and parent.kratos_sessions is IdentityRecoveryCleanupState.PENDING


@pytest.mark.asyncio
@pytest.mark.parametrize("crossed", ["worker", "fence", "attempt", "target", "payload", "deadline"])
async def test_live_suspension_authority_denies_a_crossed_context(
    database: Database, crossed: str
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    match crossed:
        case "worker":
            worker_id = uuid4()
        case "fence":
            context = replace(context, fence=JobFence(uuid4()))
        case "attempt":
            context = replace(context, attempt=context.attempt + 1)
        case "target":
            context = replace(context, binding=replace(context.binding, principal_id=uuid4()))
        case "payload":
            context = replace(context, payload=JobPayload(context.payload.kind, 1, uuid4().bytes))
        case _:
            assert crossed == "deadline"
            context = replace(context, work_deadline=context.work_deadline + timedelta(seconds=1))
    async with database.session() as session, session.begin():
        authorizer = HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        )
        with pytest.raises(AccessDeniedError):
            await authorizer.require_current(context, worker_id=worker_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("lost", ["lease", "work", "ended", "active-target", "superseded"])
async def test_live_suspension_authority_requires_a_still_applicable_open_attempt(
    database: Database, lost: str
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    async with database.session() as session, session.begin():
        row = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        target = await session.get(PrincipalRow, binding.principal_id)
        org = await session.get(OrganizationRow, binding.organization_id)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert row is not None and attempt is not None and parent is not None
        assert target is not None and org is not None and now is not None
        if lost == "lease":
            row.lease_expires_at = now - timedelta(seconds=1)
        elif lost == "work":
            deadline = now - timedelta(seconds=1)
            row.work_deadline = deadline
            context = replace(context, work_deadline=deadline)
        elif lost == "ended":
            attempt.ended_at = now
        elif lost == "active-target":
            target.status = PrincipalStatus.ACTIVE
        else:
            assert lost == "superseded"
            before = org.access_revision
            org.access_revision = before + 1
            session.add(
                replace(
                    parent,
                    id=uuid4(),
                    job_id=uuid4(),
                    operation_id="later-suspension-" + str(uuid4()),
                    request_id=uuid4(),
                    before_access_revision=before,
                    access_revision=before + 1,
                    admitted_at=parent.admitted_at,
                    queued_deadline=parent.queued_deadline,
                )
            )

    async with database.session() as session, session.begin():
        authorizer = HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        )
        with pytest.raises(AccessDeniedError):
            await authorizer.require_current(context, worker_id=worker_id)
        parent = await session.get(HumanSuspensionObligationRow, binding.obligation_id.value)
        assert parent is not None and parent.completed_at is None and parent.source_revision == 1


@pytest.mark.asyncio
async def test_already_started_suspension_attempt_outlives_original_queue_wait(
    database: Database,
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    async with database.session() as session, session.begin():
        row = await session.get(DurableJobRow, context.job_id.value)
        attempt = await session.get(DurableJobAttemptRow, (context.job_id.value, context.attempt))
        parent = await session.get(
            HumanSuspensionObligationRow, context.binding.obligation_id.value
        )
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert row is not None and parent is not None and attempt is not None and now is not None
        queue_end = now - timedelta(seconds=1)
        admitted = queue_end - timedelta(hours=24)
        parent.admitted_at, parent.queued_deadline = admitted, queue_end
        row.admitted_at, row.queued_deadline, row.due_at = admitted, queue_end, admitted
        attempt.started_at = queue_end - timedelta(seconds=2)
    async with database.session() as session, session.begin():
        facts = await HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        ).require_current(context, worker_id=worker_id)
        assert queue_end < facts.observed_at < facts.lease_expires_at <= facts.work_deadline


@pytest.mark.asyncio
async def test_live_suspension_observes_fresh_facts_after_child_wait(database: Database) -> None:
    context, worker_id = await _live_suspension_attempt(database)

    async def read() -> None:
        async with database.session() as session, session.begin():
            authorizer = HumanSuspensionJobAuthorizationService(
                PostgresHumanSuspensionJobFactsReader(session)
            )
            with pytest.raises(AccessDeniedError):
                await authorizer.require_current(context, worker_id=worker_id)

    async with asyncio.TaskGroup() as tasks, database.session() as holder, holder.begin():
        row = await holder.scalar(
            select(DurableJobRow).where(DurableJobRow.id == context.job_id.value).with_for_update()
        )
        assert row is not None
        task = tasks.create_task(read())
        await wait_for_database_lock(database, task)
        now = await holder.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        row.lease_expires_at = now - timedelta(seconds=1)


@pytest.mark.asyncio
async def test_live_suspension_observes_current_target_after_identity_wait(
    database: Database,
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding

    async def read() -> None:
        async with database.session() as session, session.begin():
            authorizer = HumanSuspensionJobAuthorizationService(
                PostgresHumanSuspensionJobFactsReader(session)
            )
            with pytest.raises(AccessDeniedError):
                await authorizer.require_current(context, worker_id=worker_id)

    async with asyncio.TaskGroup() as tasks, database.session() as holder, holder.begin():
        await PostgresIdentityCoordinator(holder).acquire(
            installation_id=binding.installation_id, identity=binding.identity
        )
        assert (
            await holder.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == binding.organization_id)
                .with_for_update()
            )
            == binding.organization_id
        )
        target = await holder.get(PrincipalRow, binding.principal_id)
        assert target is not None and target.status is PrincipalStatus.SUSPENDED
        task = tasks.create_task(read())
        await wait_for_database_lock(database, task)
        target.status = PrincipalStatus.ACTIVE


@pytest.mark.asyncio
async def test_live_suspension_authority_leaves_independent_recovery_and_initiator_alone(
    database: Database,
) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    assert isinstance(context.binding, HumanSuspensionJobBindingDTO)
    binding = context.binding
    async with database.session() as session, session.begin():
        await session.execute(
            delete(OrganizationActionGrantRow).where(
                OrganizationActionGrantRow.organization_id == binding.organization_id,
                OrganizationActionGrantRow.recipient_principal_id == binding.initiator_principal_id,
                OrganizationActionGrantRow.action == OrganizationAction.SUSPEND_USERS.value,
            )
        )
        recovery = await IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=binding.installation_id,
                authority=binding.identity.authority,
            )
        ).admit(
            IdentityRecoveryEventDTO(
                flow_id=IdentityRecoveryFlowId(uuid4()),
                identity=binding.identity,
                event_kind=IdentityRecoveryEventKind.RECOVERY,
            )
        )
    async with database.session() as session, session.begin():
        facts = await HumanSuspensionJobAuthorizationService(
            PostgresHumanSuspensionJobFactsReader(session)
        ).require_current(context, worker_id=worker_id)
        row = await session.get(IdentityRecoveryAdmissionRow, recovery.value)
        assert facts.binding == binding and row is not None and row.released_at is None


@pytest.mark.asyncio
async def test_live_suspension_requires_read_committed(database: Database) -> None:
    context, worker_id = await _live_suspension_attempt(database)
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresHumanSuspensionJobFactsReader(session).read_live_attempt(
                context, worker_id=worker_id
            )
        await session.rollback()
