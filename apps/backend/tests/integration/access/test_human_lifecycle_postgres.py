"""Exercise atomic local human lifecycle operations against PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.integration.access.test_project_deletion_postgres import (
    deletion_context,
    deletion_service,
)
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    seed_artifact_scope,
)
from tests.support.first_administrator_bootstrap_scenarios import MockBootstrapIdentityVerifier
from tests.support.project_creation_scenarios import create_project
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    change_membership,
    seed_membership_project,
)
from tests.support.spending_scenarios import wait_for_database_lock

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
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
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.human_lifecycle_fingerprint_service import (
    HumanLifecycleFingerprintService,
)
from inframeld_backend.access.application.services.human_restoration_service import (
    HumanRestorationService,
)
from inframeld_backend.access.application.services.human_suspension_service import (
    HumanSuspensionService,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.application.value_objects.security_review_reference import (
    SecurityReviewReference,
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
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_lifecycle_facts_reader import (
    PostgresHumanLifecycleFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_lifecycle_result_reader import (
    PostgresHumanLifecycleResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_lifecycle_operation_result_row import (
    HumanLifecycleOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.writers.postgres_human_lifecycle_writer import (
    PostgresHumanLifecycleWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobQueueFullError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.readers.postgres_job_queue_status_reader import (
    PostgresJobQueueStatusReader,
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
from inframeld_backend.shared.infrastructure.writers.postgres_artifact_cleanup_admission_writer import (
    PostgresArtifactCleanupAdmissionWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_suspension_commits_durable_original_with_full_ordinary_queue(
    database: Database,
) -> None:
    scope = await seed_membership_project(database)
    actor = scope.actor
    organization = actor.organization_id.value
    project = scope.project.project_id.value
    target = scope.bob_id.value
    action = OrganizationAction.SUSPEND_USERS
    evidence = scope.bob_access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    await change_membership(
        database, scope, revision=scope.project.access_revision, key="member-before-suspension"
    )
    authority = _ordinary_authority(scope)
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=project,
                recipient_principal_id=target,
                recipient_kind=PrincipalKind.HUMAN,
                action="inspect-feedback",
                can_grant=False,
                assigned_by_principal_id=authority.principal_id.value,
            )
        )
        jobs = await _fill_ordinary_queue(session, authority)

    queue = select(DurableJobRow.id, DurableJobRow.status).where(
        DurableJobRow.binding_kind != "human_suspension"
    )
    assignment = (project, target, "inspect-feedback")
    membership = (project, target)
    async with database.session() as session:
        assert len(jobs) == 8
        assert set((await session.execute(queue)).tuples()) == {
            (job_id, JobStatus.QUEUED.value) for job_id in jobs
        }
        org = await session.get(OrganizationRow, organization)
        principal = await session.get(PrincipalRow, target)
        grant = await session.get(
            OrganizationActionGrantRow, (organization, authority.principal_id.value, action.value)
        )
        assert org is not None
        assert principal is not None and principal.status is PrincipalStatus.ACTIVE
        assert grant is not None and grant.recipient_kind is PrincipalKind.HUMAN
        assert await session.get(ProjectMembershipRow, membership) is not None
        assert await session.get(ProjectActionGrantRow, assignment) is not None
        revision = org.access_revision

    command = SuspendHumanCommand(
        actor.organization_id, scope.bob_id, revision, SuspensionReason("Incident reviewed")
    )
    context = IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/organizations/{organization}/humans/{target}/suspend",
        IdempotencyKey("suspend-at-full-capacity"),
    )
    request_id = RequestId(uuid4())
    async with database.session() as session:
        result = await _suspender(session).suspend(
            access=actor.access, command=command, context=context, request_id=request_id
        )

    assert result.operation.created and result.operation.expires_at is None
    assert result.principal_id == scope.bob_id and result.access_revision == revision + 1
    operation_id = result.operation.operation_id.value
    async with database.session() as session:
        org = await session.get(OrganizationRow, organization)
        principal = await session.get(PrincipalRow, target)
        assert org is not None and org.access_revision == revision + 1
        assert principal is not None and principal.status is PrincipalStatus.SUSPENDED
        assert set((await session.execute(queue)).tuples()) == {
            (job_id, JobStatus.QUEUED.value) for job_id in jobs
        }
        assert await session.get(ProjectMembershipRow, membership) is not None
        assert await session.get(ProjectActionGrantRow, assignment) is not None

        original = await session.get(IdempotencyReservationRow, operation_id)
        saved = await session.get(HumanLifecycleOperationResultRow, operation_id)
        assert original is not None and original.state is OperationReservationState.REPLAYABLE
        assert original.replay_kind is OperationReplayKind.ASYNC_JOB
        assert original.project_id is None and original.request_key == context.key.value
        assert original.requested_route == context.requested_route
        assert original.lookup_action_id == action.value
        assert saved is not None and saved.changed and saved.action_id is action
        assert saved.before_revision == revision and saved.access_revision == revision + 1
        assert (
            saved.principal_id == target
            and saved.actor_principal_id == authority.principal_id.value
        )

        obligation = (
            await session.scalars(
                select(HumanSuspensionObligationRow).where(
                    HumanSuspensionObligationRow.organization_id == organization,
                    HumanSuspensionObligationRow.principal_id == target,
                )
            )
        ).one()
        assert str(obligation.id) == result.cleanup_operation_id.value
        assert saved.cleanup_operation_id == obligation.id
        assert obligation.operation_id == operation_id and obligation.request_id == request_id.value
        assert obligation.installation_id == authority.installation_id.value
        assert (obligation.authority, obligation.subject) == (
            evidence.identity.authority.value,
            evidence.identity.subject.value,
        )
        assert obligation.initiator_principal_id == authority.principal_id.value
        assert obligation.request_key == original.request_key
        assert obligation.request_fingerprint == original.request_fingerprint
        assert obligation.before_access_revision == revision
        assert obligation.access_revision == revision + 1
        assert obligation.queued_deadline == obligation.admitted_at + timedelta(hours=24)
        assert obligation.job_id not in jobs
        assert obligation.queue_exhausted_at is None and obligation.completed_at is None
        assert (
            obligation.kratos_sessions,
            obligation.hydra_cli_grants,
            obligation.hydra_remembered_logins,
        ) == (IdentityRecoveryCleanupState.PENDING,) * 3

        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.organization_id == organization,
                    AccessAuditEventRow.target_id == target,
                    AccessAuditEventRow.correlation_id == operation_id,
                )
            )
        ).one()
        assert audit.actor_principal_id == authority.principal_id.value
        assert audit.reason == command.reason.value

        child = await session.get(DurableJobRow, obligation.job_id)
        assert child is not None, "Suspension must commit its fixed cleanup job with the original."
        assert child.binding_kind == "human_suspension"
        assert child.suspension_obligation_id == obligation.id
        assert child.operation_id is None and child.project_id is None
        assert child.principal_id is None and child.action_id is None
        assert (
            child.installation_id,
            child.organization_id,
            child.request_id,
        ) == (obligation.installation_id, obligation.organization_id, obligation.request_id)
        assert (child.payload_kind, child.payload_version, child.payload) == (
            "human.suspension-cleanup",
            1,
            obligation.id.bytes,
        )
        assert child.admitted_at == child.due_at == obligation.admitted_at
        assert child.queued_deadline == obligation.queued_deadline
        assert child.status == JobStatus.QUEUED.value and child.attempt_count == 0
        assert child.worker_id is None and child.fence is None and child.lease_expires_at is None
        assert child.work_deadline is None and child.terminal_at is None
        assert child.pending_effect is None
        assert (
            await session.scalar(
                select(DurableJobAttemptRow.number).where(DurableJobAttemptRow.job_id == child.id)
            )
            is None
        )

        pressure = await PostgresJobQueueStatusReader(session).read()
        assert pressure.depth == len(jobs) and not pressure.active
        next_ordinary = await PostgresJobStore(session).peek_candidate()
        assert next_ordinary is not None and next_ordinary.job_id.value in jobs


def _ordinary_authority(scope: MembershipProjectSeedDTO) -> AdmittedWorkAuthorityDTO:
    actor = scope.actor
    return AdmittedWorkAuthorityDTO(
        principal_id=actor.access.actor_principal_id,
        principal_kind=PrincipalKind.HUMAN,
        installation_id=actor.binding.installation_id,
        organization_id=actor.organization_id,
        project_id=scope.project.project_id,
        action_id=ActionId("inspect-feedback"),
        human_binding=actor.binding,
    )


async def _fill_ordinary_queue(
    session: AsyncSession,
    authority: AdmittedWorkAuthorityDTO,
    *,
    slots: int = 8,
    capacity: int = 8,
) -> set[UUID]:
    jobs: set[UUID] = set()
    writer = PostgresOperationReservationWriter(session)
    store = PostgresJobStore(session)
    for slot in range(slots):
        reservation = await writer.reserve(
            OperationReservationRequestDTO(
                principal_id=authority.principal_id,
                organization_id=authority.organization_id,
                project_id=authority.project_id,
                method=HttpMethod.POST,
                requested_route=f"/test/projects/{authority.project_id.value}/feedback-reports",
                key=IdempotencyKey(f"ordinary-job-{slot}"),
                fingerprint=b"F" * 32,
            )
        )
        job = await store.admit(
            operation_id=reservation.operation_id,
            request_id=RequestId(uuid4()),
            authority=authority,
            payload=JobPayload("test.progress", 1, b"fixed"),
            capacity=capacity,
        )
        await writer.mark_replayable(reservation.operation_id, OperationReplayKind.ASYNC_JOB)
        jobs.add(job.job_id.value)
    return jobs


@pytest.mark.asyncio
async def test_two_private_suspension_jobs_survive_ordinary_cancellation(
    database: Database,
) -> None:
    scope = await seed_membership_project(database)
    async with database.session() as session, session.begin():
        jobs = await _fill_ordinary_queue(session, _ordinary_authority(scope))
    oldest = await _suspend(database, scope, await _revision(database, scope))
    actor = scope.actor
    actor_id = actor.access.actor_principal_id
    younger_command = replace(
        _suspend_command(scope, oldest.access_revision), principal_id=actor_id
    )
    async with database.session() as session:
        younger = await _suspender(session).suspend(
            access=actor.access,
            command=younger_command,
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/organizations/{actor.organization_id.value}/humans/{actor_id.value}/suspend",
                IdempotencyKey("later-suspension"),
            ),
            request_id=RequestId(uuid4()),
        )
    assert oldest.operation.created and younger.operation.created
    first_id = UUID(oldest.cleanup_operation_id.value)
    second_id = UUID(younger.cleanup_operation_id.value)
    queue = select(DurableJobRow.id, DurableJobRow.status).where(
        DurableJobRow.binding_kind != "human_suspension"
    )
    async with database.session() as session, session.begin():
        assert len(jobs) == 8
        assert set((await session.execute(queue)).tuples()) == {
            (job_id, JobStatus.QUEUED.value) for job_id in jobs
        }
        first = await session.get(HumanSuspensionObligationRow, first_id)
        second = await session.get(HumanSuspensionObligationRow, second_id)
        assert first is not None and second is not None
        assert first.admitted_at < second.admitted_at
        for parent in (first, second):
            assert parent.queued_deadline == parent.admitted_at + timedelta(hours=24)
            assert parent.job_id not in jobs
            child = await session.get(DurableJobRow, parent.job_id)
            assert child is not None and child.status == JobStatus.QUEUED.value
            assert child.suspension_obligation_id == parent.id
            assert child.due_at == parent.admitted_at and child.attempt_count == 0
        private_ids = {first.job_id, second.job_id}

        store = PostgresJobStore(session)
        observed = await store.peek_candidate()
        assert observed is not None and observed.job_id.value in jobs
        await store.request_cancel(observed.job_id)
        canceled = await store.next_candidate()
        assert canceled is not None and canceled.job_id == observed.job_id
        assert canceled.cancel_requested
        await store.retire_attempt(
            canceled,
            status=JobStatus.CANCELED,
            reason="cancellation_requested",
            due_at=canceled.observed_at,
        )

    ordinary_queue_after_cancel = {
        (ordinary_job_id, JobStatus.QUEUED.value)
        for ordinary_job_id in jobs
        if ordinary_job_id != canceled.job_id.value
    } | {(canceled.job_id.value, JobStatus.CANCELED.value)}
    async with database.session() as session:
        assert set((await session.execute(queue)).tuples()) == ordinary_queue_after_cancel
        children = (
            await session.scalars(
                select(DurableJobRow).where(DurableJobRow.binding_kind == "human_suspension")
            )
        ).all()
        assert {child.id for child in children} == private_ids
        assert all(
            child.status == JobStatus.QUEUED.value
            and child.attempt_count == 0
            and not child.cancel_requested
            for child in children
        )


def _fingerprints() -> HumanLifecycleFingerprintService:
    return HumanLifecycleFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"H" * 32))
    )


def _suspender(
    session: AsyncSession, *, writer: PostgresHumanLifecycleWriter | None = None
) -> HumanSuspensionService:
    return HumanSuspensionService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        lifecycle_facts_reader=PostgresHumanLifecycleFactsReader(session),
        lifecycle_writer=PostgresHumanLifecycleWriter(session) if writer is None else writer,
        lifecycle_result_reader=PostgresHumanLifecycleResultReader(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        lifecycle_fingerprint_service=_fingerprints(),
    )


def _restorer(
    session: AsyncSession, *, writer: PostgresHumanLifecycleWriter | None = None
) -> HumanRestorationService:
    class Verifier(MockBootstrapIdentityVerifier):
        @override
        async def verify(
            self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
        ) -> VerifiedHumanIdentityDTO | None:
            assert not session.in_transaction() and timeout_seconds <= 5
            return await super().verify(identity, timeout_seconds=timeout_seconds)

    return HumanRestorationService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        lifecycle_facts_reader=PostgresHumanLifecycleFactsReader(session),
        lifecycle_writer=PostgresHumanLifecycleWriter(session) if writer is None else writer,
        lifecycle_result_reader=PostgresHumanLifecycleResultReader(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        lifecycle_fingerprint_service=_fingerprints(),
        identity_verifier=Verifier(),
    )


def _context(scope: MembershipProjectSeedDTO, *, action: str, key: str) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/organizations/{scope.actor.organization_id.value}/humans/{scope.bob_id.value}/{action}",
        IdempotencyKey(key),
    )


async def _revision(database: Database, scope: MembershipProjectSeedDTO) -> int:
    async with database.session() as session:
        row = await session.get(OrganizationRow, scope.actor.organization_id.value)
        assert row is not None
        return row.access_revision


def _suspend_command(scope: MembershipProjectSeedDTO, revision: int) -> SuspendHumanCommand:
    return SuspendHumanCommand(
        scope.actor.organization_id, scope.bob_id, revision, SuspensionReason("Incident reviewed")
    )


async def _suspend(
    database: Database, scope: MembershipProjectSeedDTO, revision: int, *, key: str = "suspension"
) -> HumanSuspensionResultDTO:
    async with database.session() as session:
        return await _suspender(session).suspend(
            access=scope.actor.access,
            command=_suspend_command(scope, revision),
            context=_context(scope, action="suspend", key=key),
            request_id=RequestId(uuid4()),
        )


async def _confirm_cleanup(database: Database, result: HumanSuspensionResultDTO) -> None:
    """Install the local completion facts of the original for this SQL-only test."""
    async with database.session() as session, session.begin():
        row = await session.get(
            HumanSuspensionObligationRow, UUID(result.cleanup_operation_id.value)
        )
        assert row is not None
        row.kratos_sessions = IdentityRecoveryCleanupState.CONFIRMED
        row.hydra_cli_grants = IdentityRecoveryCleanupState.CONFIRMED
        row.hydra_remembered_logins = IdentityRecoveryCleanupState.CONFIRMED
        row.completed_at = row.admitted_at


async def _assert_no_suspension_effects(
    database: Database, scope: MembershipProjectSeedDTO, revision: int
) -> None:
    assert await _revision(database, scope) == revision
    async with database.session() as session:
        target = await session.get(PrincipalRow, scope.bob_id.value)
        assert target is not None and target.status is PrincipalStatus.ACTIVE
        assert not (await session.scalars(select(HumanSuspensionObligationRow.id))).all()
        assert not (
            await session.scalars(
                select(DurableJobRow.id).where(DurableJobRow.binding_kind == "human_suspension")
            )
        ).all()
        assert not (
            await session.scalars(select(HumanLifecycleOperationResultRow.operation_id))
        ).all()
        assert not (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.requested_route.like("%/suspend")
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.target_id == scope.bob_id.value,
                    AccessAuditEventRow.action == OrganizationAction.SUSPEND_USERS.value,
                )
            )
        ).all()


@pytest.mark.asyncio
async def test_suspension_replay_requires_current_authority_and_keeps_one_obligation(
    database: Database,
) -> None:
    scope = await seed_membership_project(database)
    revision = await _revision(database, scope)
    first = await _suspend(database, scope, revision)
    replay = await _suspend(database, scope, revision)
    assert (
        not replay.operation.created
        and replay.operation.operation_id == first.operation.operation_id
    )
    assert (replay.cleanup_operation_id, replay.access_revision) == (
        first.cleanup_operation_id,
        first.access_revision,
    )
    noop = await _suspend(database, scope, first.access_revision, key="already-suspended")
    assert noop.operation.created and noop.operation.operation_id != first.operation.operation_id
    assert (noop.cleanup_operation_id, noop.access_revision) == (
        first.cleanup_operation_id,
        first.access_revision,
    )
    async with database.session() as session, session.begin():
        parent = (await session.scalars(select(HumanSuspensionObligationRow))).one()
        child = (await session.scalars(select(DurableJobRow))).one()
        assert child.id == parent.job_id and child.suspension_obligation_id == parent.id
        await session.execute(
            delete(OrganizationActionGrantRow).where(
                OrganizationActionGrantRow.organization_id == scope.actor.organization_id.value,
                OrganizationActionGrantRow.recipient_principal_id
                == scope.actor.access.actor_principal_id.value,
                OrganizationActionGrantRow.action == OrganizationAction.SUSPEND_USERS.value,
            )
        )
    with pytest.raises(AccessDeniedError):
        await _suspend(database, scope, revision)
    assert await _revision(database, scope) == first.access_revision


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction", ["pending", "failed", "uncertain", "independent-recovery"])
async def test_restoration_requires_original_cleanup_and_no_independent_block(
    database: Database, restriction: str
) -> None:
    scope = await seed_membership_project(database)
    original = await _suspend(database, scope, await _revision(database, scope))
    evidence = scope.bob_access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    if restriction == "independent-recovery":
        await _confirm_cleanup(database, original)
        async with database.session() as session, session.begin():
            await IdentityRecoveryAdmissionService(
                PostgresIdentityRecoveryAdmissionWriter(
                    session,
                    installation_id=evidence.installation_id,
                    authority=evidence.identity.authority,
                )
            ).admit(
                IdentityRecoveryEventDTO(
                    flow_id=IdentityRecoveryFlowId(uuid4()),
                    identity=evidence.identity,
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )
    elif restriction != "pending":
        async with database.session() as session, session.begin():
            row = await session.get(
                HumanSuspensionObligationRow, UUID(original.cleanup_operation_id.value)
            )
            assert row is not None
            row.kratos_sessions = IdentityRecoveryCleanupState(restriction)
            row.hydra_cli_grants = IdentityRecoveryCleanupState.CONFIRMED
            row.hydra_remembered_logins = IdentityRecoveryCleanupState.CONFIRMED
    command = RestoreHumanCommand(
        scope.actor.organization_id,
        scope.bob_id,
        original.access_revision,
        SecurityReviewReference("incident/42"),
    )
    context = _context(scope, action="restore", key="blocked-restore")
    versions = PostgresHumanCredentialStateReader(database)
    version = (await versions.read(evidence.identity)).version
    async with database.session() as session:
        with pytest.raises(ConflictError, match="Required cleanup or a newer recovery"):
            await _restorer(session).restore(
                access=scope.actor.access, command=command, context=context
            )
    assert await _revision(database, scope) == original.access_revision
    assert (await versions.read(evidence.identity)).version == version
    async with database.session() as session:
        target = await session.get(PrincipalRow, scope.bob_id.value)
        assert target is not None and target.status is PrincipalStatus.SUSPENDED
        assert not (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.request_key == context.key.value
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(HumanLifecycleOperationResultRow.operation_id).where(
                    HumanLifecycleOperationResultRow.action_id == OrganizationAction.RESTORE_USERS
                )
            )
        ).all()


@pytest.mark.asyncio
async def test_restoration_advances_version_once_and_replays_without_reactivating_later_block(
    database: Database,
) -> None:
    scope = await seed_membership_project(database)
    evidence = scope.bob_access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    membership = await change_membership(
        database, scope, revision=scope.project.access_revision, key="before-incident"
    )
    original = await _suspend(database, scope, await _revision(database, scope))
    removed = await change_membership(
        database, scope, revision=membership.access_revision, key="during-incident", remove=True
    )
    assert removed.changed
    await _confirm_cleanup(database, original)
    command = RestoreHumanCommand(
        scope.actor.organization_id,
        scope.bob_id,
        original.access_revision,
        SecurityReviewReference("incident/42"),
    )
    context = _context(scope, action="restore", key="restore-once")
    async with database.session() as session:
        restored = await _restorer(session).restore(
            access=scope.actor.access, command=command, context=context
        )
    assert restored.operation.created and restored.operation.expires_at is not None
    assert restored.access_revision == original.access_revision + 1
    assert restored.credential_version.value == evidence.version.value + 1
    assert (
        await PostgresHumanCredentialStateReader(database).read(evidence.identity)
    ).version == restored.credential_version
    async with database.session() as session:
        target = await session.get(PrincipalRow, scope.bob_id.value)
        assert target is not None and target.status is PrincipalStatus.ACTIVE
        assert (
            await session.get(
                ProjectMembershipRow, (scope.project.project_id.value, scope.bob_id.value)
            )
            is None
        )
        stored = await session.get(
            HumanLifecycleOperationResultRow, restored.operation.operation_id.value
        )
        assert stored is not None and stored.changed
        assert stored.cleanup_operation_id == UUID(original.cleanup_operation_id.value)
        assert (stored.before_credential_version, stored.credential_version) == (
            evidence.version.value,
            restored.credential_version.value,
        )
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == restored.operation.operation_id.value
                )
            )
        ).one()
        assert audit.reason == command.security_review_reference.value
        assert audit.action == OrganizationAction.RESTORE_USERS.value

    async with database.session() as session:
        noop = await _restorer(session).restore(
            access=scope.actor.access,
            command=replace(command, expected_access_revision=restored.access_revision),
            context=_context(scope, action="restore", key="already-active"),
        )
        saved_noop = await session.get(
            HumanLifecycleOperationResultRow, noop.operation.operation_id.value
        )
        assert saved_noop is not None and not saved_noop.changed
    assert noop.operation.created
    assert (noop.credential_version, noop.access_revision) == (
        restored.credential_version,
        restored.access_revision,
    )

    oauth = AccessContextDTO(
        scope.bob_id,
        HumanOAuthCredentialBindingDTO(
            evidence.identity, evidence.installation_id, evidence.version
        ),
    )
    for stale, error in (
        (scope.bob_access, AuthenticationRequiredError),
        (oauth, HumanOAuthCredentialRejectedError),
    ):
        async with database.session() as session:
            with pytest.raises(error) as failure:
                await _restorer(session).restore(access=stale, command=command, context=context)
            assert type(failure.value) is error

    later = await _suspend(database, scope, restored.access_revision, key="later-incident")
    async with database.session() as session:
        replay = await _restorer(session).restore(
            access=scope.actor.access, command=command, context=context
        )
        target = await session.get(PrincipalRow, scope.bob_id.value)
        assert target is not None and target.status is PrincipalStatus.SUSPENDED
    assert not replay.operation.created
    assert replay.operation.operation_id == restored.operation.operation_id
    assert replay.operation.expires_at == restored.operation.expires_at
    assert (replay.access_revision, replay.credential_version) == (
        restored.access_revision,
        restored.credential_version,
    )
    assert await _revision(database, scope) == later.access_revision
    assert (
        await PostgresHumanCredentialStateReader(database).read(evidence.identity)
    ).version == restored.credential_version


@pytest.mark.asyncio
@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_lifecycle_identity_turn_requires_read_committed(
    database: Database, isolation: str
) -> None:
    scope = await seed_membership_project(database)
    evidence = scope.bob_access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresHumanLifecycleFactsReader(session).lock_for_change(
                access=scope.actor.access,
                organization_id=scope.actor.organization_id,
                principal_id=scope.bob_id,
                action_id=ActionId(OrganizationAction.SUSPEND_USERS.value),
                identity=evidence.identity,
            )
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("blocking", ["identity", "organization", "cancel"])
async def test_suspension_rereads_after_wait_or_cancels_without_effects(
    database: Database, blocking: str
) -> None:
    scope = await seed_membership_project(database)
    evidence = scope.bob_access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    revision = await _revision(database, scope)
    org = scope.actor.organization_id.value

    async def suspend_while_waiting() -> None:
        if blocking == "cancel":
            await _suspend(database, scope, revision)
        else:
            with pytest.raises(AccessDeniedError):
                await _suspend(database, scope, revision)

    async with asyncio.TaskGroup() as tasks, database.session() as holder, holder.begin():
        lock_org = select(OrganizationRow.id).where(OrganizationRow.id == org).with_for_update()
        if blocking == "identity":
            await PostgresIdentityCoordinator(holder).acquire(
                installation_id=evidence.installation_id, identity=evidence.identity
            )
        else:
            assert await holder.scalar(lock_org) == org
        task = tasks.create_task(suspend_while_waiting())
        await wait_for_database_lock(database, task)
        if blocking == "cancel":
            task.cancel()
        else:
            if blocking == "identity":
                assert await holder.scalar(lock_org) == org
            await holder.execute(
                delete(OrganizationActionGrantRow).where(
                    OrganizationActionGrantRow.organization_id == org,
                    OrganizationActionGrantRow.recipient_principal_id
                    == scope.actor.access.actor_principal_id.value,
                    OrganizationActionGrantRow.action == OrganizationAction.SUSPEND_USERS.value,
                )
            )
    if blocking == "cancel":
        assert task.cancelled()
    await _assert_no_suspension_effects(database, scope, revision)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["before-commit", "lost-ack"])
@pytest.mark.parametrize("action", ["suspend", "restore"])
async def test_lifecycle_rolls_back_or_recovers_one_original_at_commit(
    database: Database, fault: str, action: str
) -> None:
    scope = await seed_membership_project(database)
    revision = await _revision(database, scope)
    evidence = scope.bob_access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    if action == "restore":
        original = await _suspend(database, scope, revision, key="before-restore")
        await _confirm_cleanup(database, original)
        revision = original.access_revision
    restore = RestoreHumanCommand(
        scope.actor.organization_id, scope.bob_id, revision, SecurityReviewReference("incident/42")
    )
    context = _context(scope, action=action, key="fault-original")

    async with database.session() as session:

        class FaultWriter(PostgresHumanLifecycleWriter):
            @override
            async def save_result(
                self,
                *,
                facts: HumanLifecycleFactsDTO,
                result: HumanSuspensionResultDTO | HumanRestorationResultDTO,
            ) -> None:
                await super().save_result(facts=facts, result=result)
                if fault == "before-commit":
                    raise ConnectionError("Controlled failure before commit")

                def lose_ack(_session: Session) -> None:
                    raise ConnectionError("Controlled lost commit acknowledgment")

                event.listen(session.sync_session, "after_commit", lose_ack, once=True)

        with pytest.raises(ConnectionError, match="Controlled"):
            writer = FaultWriter(session)
            if action == "suspend":
                await _suspender(session, writer=writer).suspend(
                    access=scope.actor.access,
                    command=_suspend_command(scope, revision),
                    context=context,
                    request_id=RequestId(uuid4()),
                )
            else:
                await _restorer(session, writer=writer).restore(
                    access=scope.actor.access, command=restore, context=context
                )

    if action == "suspend":
        if fault == "before-commit":
            await _assert_no_suspension_effects(database, scope, revision)
            return
        replay = await _suspend(database, scope, revision, key=context.key.value)
        assert not replay.operation.created and replay.access_revision == revision + 1
        async with database.session() as session:
            obligation = (await session.scalars(select(HumanSuspensionObligationRow))).one()
            result = (await session.scalars(select(HumanLifecycleOperationResultRow))).one()
            child = (await session.scalars(select(DurableJobRow))).one()
            assert (
                obligation.operation_id
                == result.operation_id
                == replay.operation.operation_id.value
            )
            assert str(obligation.id) == replay.cleanup_operation_id.value
            assert child.id == obligation.job_id and child.suspension_obligation_id == obligation.id
        return

    committed = fault == "lost-ack"
    assert await _revision(database, scope) == revision + int(committed)
    observed = await PostgresHumanCredentialStateReader(database).read(evidence.identity)
    assert observed.version is not None and observed.version.value == evidence.version.value + int(
        committed
    )
    async with database.session() as session:
        target = await session.get(PrincipalRow, scope.bob_id.value)
        assert target is not None and target.status is (
            PrincipalStatus.ACTIVE if committed else PrincipalStatus.SUSPENDED
        )
        original_rows = (
            await session.scalars(
                select(HumanLifecycleOperationResultRow).where(
                    HumanLifecycleOperationResultRow.action_id == OrganizationAction.RESTORE_USERS
                )
            )
        ).all()
        reservation_rows = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.request_key == context.key.value
                )
            )
        ).all()
        audit_rows = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.action == OrganizationAction.RESTORE_USERS.value
                )
            )
        ).all()
        assert len(original_rows) == len(reservation_rows) == len(audit_rows) == int(committed)
        if committed:
            assert (
                original_rows[0].operation_id
                == reservation_rows[0].operation_id
                == audit_rows[0].correlation_id
            )
    if committed:
        async with database.session() as session:
            recovered = await _restorer(session).restore(
                access=scope.actor.access, command=restore, context=context
            )
        assert not recovered.operation.created
        assert recovered.operation.operation_id.value == original_rows[0].operation_id
        assert (recovered.credential_version, recovered.access_revision) == (
            observed.version,
            revision + 1,
        )
        assert (
            await PostgresHumanCredentialStateReader(database).read(evidence.identity)
        ).version == observed.version


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["product", "artifact", "project-deletion"])
async def test_private_suspension_does_not_consume_any_ordinary_admission_slot(
    database: Database, boundary: str
) -> None:
    scope = await seed_membership_project(database)
    spare_project = None
    if boundary == "project-deletion":
        spare_project = (
            await create_project(
                database,
                replace(scope.actor, access_revision=await _revision(database, scope)),
                name="other",
                key="other-project",
            )
        ).project
    await _suspend(database, scope, await _revision(database, scope))

    if boundary == "artifact":
        artifact = await seed_artifact_scope(database)
        original = await allocate_artifact(database, artifact_scenario(artifact), capacity=1)
        async with database.session() as session, session.begin():
            replay = await PostgresArtifactCleanupAdmissionWriter(session).admit(
                original.cleanup_binding, capacity=1
            )
            assert replay.job_id == original.cleanup_job_id and not replay.created
        with pytest.raises(JobQueueFullError):
            await allocate_artifact(database, artifact_scenario(artifact), capacity=1)
    elif boundary == "project-deletion":
        assert spare_project is not None
        project = scope.project
        command = DeleteProjectCommand(project.project_id, project.access_revision)
        context = deletion_context(project.project_id)
        async with database.session() as session:
            accepted = await deletion_service(session, capacity=1).delete(
                access=scope.actor.access,
                command=command,
                context=context,
                request_id=RequestId(uuid4()),
            )
            replay = await deletion_service(session, capacity=1).delete(
                access=scope.actor.access,
                command=command,
                context=context,
                request_id=RequestId(uuid4()),
            )
        assert not replay.operation.created and replay.job_id == accepted.job_id
        async with database.session() as session:
            with pytest.raises(JobQueueFullError):
                await deletion_service(session, capacity=1).delete(
                    access=scope.actor.access,
                    command=DeleteProjectCommand(
                        spare_project.project_id, spare_project.access_revision
                    ),
                    context=deletion_context(spare_project.project_id, key="another-deletion"),
                    request_id=RequestId(uuid4()),
                )
    else:
        authority = _ordinary_authority(scope)
        access = AccessContextDTO(authority.principal_id, scope.actor.binding)

        async def admit(key: str) -> JobAdmissionDTO:
            async with database.session() as session, session.begin():
                return await JobAdmissionService(
                    ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
                    AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                    IdempotencyService(PostgresOperationReservationWriter(session)),
                    PostgresJobStore(session),
                    PostgresJobAdmissionAuditWriter(session),
                    supported_payloads=(("test.progress", 1),),
                    capacity=1,
                ).admit(
                    access=access,
                    authority=authority,
                    context=IdempotencyContextDTO(
                        HttpMethod.POST,
                        f"/test/projects/{authority.project_id.value}/feedback-reports",
                        IdempotencyKey(key),
                    ),
                    fingerprint=RequestFingerprint(b"F" * 32),
                    request_id=RequestId(uuid4()),
                    payload=JobPayload("test.progress", 1, b"fixed"),
                )

        accepted = await admit("original-job")
        replay = await admit("original-job")
        assert not replay.created and replay.job_id == accepted.job_id
        assert replay.operation_id == accepted.operation_id
        with pytest.raises(JobQueueFullError):
            await admit("later-job")

    async with database.session() as session:
        kinds = {
            "product": "product",
            "artifact": "artifact_cleanup",
            "project-deletion": "project_deletion",
        }
        assert sorted(await session.scalars(select(DurableJobRow.binding_kind))) == sorted(
            ("human_suspension", kinds[boundary])
        )
        parent = (await session.scalars(select(HumanSuspensionObligationRow))).one()
        child = await session.get(DurableJobRow, parent.job_id)
        assert child is not None and child.status == JobStatus.QUEUED.value
        assert child.attempt_count == 0 and parent.completed_at is None


@pytest.mark.asyncio
async def test_concurrent_suspension_replay_keeps_one_fixed_child(database: Database) -> None:
    scope = await seed_membership_project(database)
    revision = await _revision(database, scope)
    async with asyncio.TaskGroup() as group:
        first = group.create_task(_suspend(database, scope, revision))
        second = group.create_task(_suspend(database, scope, revision))
    one, two = first.result(), second.result()
    assert one.operation.created != two.operation.created
    assert one.operation.operation_id == two.operation.operation_id
    assert one.cleanup_operation_id == two.cleanup_operation_id
    assert one.access_revision == two.access_revision == revision + 1

    async with database.session() as session:
        parent = (await session.scalars(select(HumanSuspensionObligationRow))).one()
        child = (await session.scalars(select(DurableJobRow))).one()
        assert str(parent.id) == one.cleanup_operation_id.value
        assert child.id == parent.job_id and child.suspension_obligation_id == parent.id
        assert child.status == JobStatus.QUEUED.value and child.attempt_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["queued", "running", "expired"])
async def test_private_suspension_is_invisible_to_ordinary_execution(
    database: Database, state: str
) -> None:
    scope = await seed_membership_project(database)
    original = await _suspend(database, scope, await _revision(database, scope))
    async with database.session() as session, session.begin():
        parent = await session.get(
            HumanSuspensionObligationRow, UUID(original.cleanup_operation_id.value)
        )
        assert parent is not None
        child = await session.get(DurableJobRow, parent.job_id)
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert child is not None and now is not None
        if state == "running":
            fence, worker_id = uuid4(), uuid4()
            child.status = JobStatus.RUNNING.value
            child.attempt_count = 1
            child.fence = fence
            child.worker_id = worker_id
            child.lease_expires_at = now + timedelta(seconds=30)
            child.work_deadline = now + timedelta(minutes=2)
            session.add(
                DurableJobAttemptRow(
                    job_id=child.id,
                    number=1,
                    fence=fence,
                    worker_id=worker_id,
                    started_at=now,
                )
            )
        elif state == "expired":
            deadline = now - timedelta(seconds=1)
            admitted = deadline - timedelta(hours=24)
            parent.admitted_at, parent.queued_deadline = admitted, deadline
            child.admitted_at, child.queued_deadline, child.due_at = admitted, deadline, admitted
        snapshot = JobSnapshotDTO(
            job_id=JobId(child.id),
            binding=PostgresJobBindingMapper.human_suspension(parent),
            payload=JobPayload(child.payload_kind, child.payload_version, child.payload),
            status=JobStatus(child.status),
            admitted_at=child.admitted_at,
            queued_deadline=child.queued_deadline,
            due_at=child.due_at,
            observed_at=now,
            attempt=child.attempt_count,
            work_deadline=child.work_deadline,
            fence=None if child.fence is None else JobFence(child.fence),
            lease_expires_at=child.lease_expires_at,
            cancel_requested=child.cancel_requested,
            pending_effect=child.pending_effect,
            reason=child.reason,
            checkpoint=child.checkpoint,
        )

    async with database.session() as session, session.begin():
        store = PostgresJobStore(session)
        assert await store.peek_candidate() is None
        assert await store.find(original.operation.operation_id) is None
        pressure = await PostgresJobQueueStatusReader(session).read()
        assert pressure.depth == 0 and not pressure.active
        assert pressure.oldest_eligible_age_seconds is None
        with pytest.raises(ConflictError):
            await store.start_attempt(
                snapshot, worker_id=uuid4(), lease_seconds=10, work_seconds=60
            )
        with pytest.raises(JobFenceLostError):
            await store.retire_attempt(
                snapshot,
                status=JobStatus.SUCCEEDED,
                reason="cleanup_already_complete",
                due_at=snapshot.observed_at,
            )
        await store.request_cancel(snapshot.job_id)

        ordinary = await _fill_ordinary_queue(
            session, _ordinary_authority(scope), slots=1, capacity=1
        )
        candidate = await store.next_candidate()
        assert candidate is not None and candidate.job_id.value in ordinary
        attempt = await store.start_attempt(
            candidate, worker_id=uuid4(), lease_seconds=10, work_seconds=60
        )
        assert attempt.job_id == candidate.job_id
        pressure = await PostgresJobQueueStatusReader(session).read()
        assert pressure.depth == 1 and pressure.active

    async with database.session() as session:
        child = await session.get(DurableJobRow, snapshot.job_id.value)
        parent = await session.get(
            HumanSuspensionObligationRow, UUID(original.cleanup_operation_id.value)
        )
        assert child is not None and parent is not None
        assert (
            JobStatus(child.status) is snapshot.status and child.attempt_count == snapshot.attempt
        )
        assert child.fence == (None if snapshot.fence is None else snapshot.fence.value)
        assert not child.cancel_requested and child.terminal_at is None
        assert parent.completed_at is None and parent.queue_exhausted_at is None


@pytest.mark.asyncio
async def test_ordinary_admission_requires_read_committed_with_private_cleanup(
    database: Database,
) -> None:
    scope = await seed_membership_project(database)
    original = await _suspend(database, scope, await _revision(database, scope))
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await _fill_ordinary_queue(session, _ordinary_authority(scope), slots=1, capacity=2)
        await session.rollback()
    async with database.session() as session:
        child = (await session.scalars(select(DurableJobRow))).one()
        parent = await session.get(
            HumanSuspensionObligationRow, UUID(original.cleanup_operation_id.value)
        )
        assert parent is not None and child.id == parent.job_id
        assert child.status == JobStatus.QUEUED.value and child.attempt_count == 0
