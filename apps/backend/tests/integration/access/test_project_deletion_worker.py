"""Qualify the real fenced child while its original physical-cleanup parent stays pending."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, delete, func, select, update
from tests.integration.access.test_project_deletion_postgres import (
    DeletionScenario,
    admit_deletion,
    deletion_context,
    deletion_service,
    seed_deletion_scenario,
)
from tests.support.application_worker_process import application_worker_process
from tests.support.project_creation_scenarios import create_project, seed_project_creator
from tests.support.seaweedfs_fixture import storage_settings

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.project_deletion_shutdown_facts_dto import (
    ProjectDeletionShutdownFactsDTO,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.deletion_status_authorization_service import (
    DeletionStatusAuthorizationService,
)
from inframeld_backend.access.application.services.project_deletion_job_handler import (
    ProjectDeletionJobHandler,
)
from inframeld_backend.access.application.services.project_deletion_shutdown_service import (
    ProjectDeletionShutdownService,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_deletion_status_facts_reader import (
    PostgresDeletionStatusFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.access.infrastructure.rows.project_upload_default_result_row import (
    ProjectUploadDefaultResultRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_application_shutdown_effects_writer import (
    PostgresProjectApplicationShutdownEffectsWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_deletion_shutdown_writer import (
    PostgresProjectDeletionShutdownWriter,
)
from inframeld_backend.bootstrap.application_worker_application_settings import (
    ApplicationWorkerApplicationSettings,
)
from inframeld_backend.bootstrap.application_worker_operations import ApplicationWorkerOperations
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.services.deletion_status_read_service import (
    DeletionStatusReadService,
)
from inframeld_backend.shared.application.services.job_continuation_eligibility_service import (
    JobContinuationEligibilityService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.services.job_recovery_service import JobRecoveryService
from inframeld_backend.shared.application.services.project_deletion_job_authorization_service import (
    ProjectDeletionJobAuthorizationService,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_facts_reader import (
    PostgresArtifactCleanupFactsReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_deletion_status_reader import (
    PostgresDeletionStatusReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_project_deletion_job_facts_reader import (
    PostgresProjectDeletionJobFactsReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
SUPPORTED = (("project.application-shutdown", 1),)


@pytest_asyncio.fixture
async def deletion_scope(database: Database) -> DeletionScenario:
    return await seed_deletion_scenario(database)


def worker_settings(settings: DatabaseSettings) -> ApplicationWorkerApplicationSettings:
    return ApplicationWorkerApplicationSettings(
        database=settings, artifact_storage=storage_settings(), jobs=JobSettings(work_seconds=60)
    )


async def claim_next(database: Database) -> JobAttemptContextDTO | None:
    """Use the production executor, authorizers and queue without a parallel worker loop."""
    async with database.session() as session:
        jobs = PostgresJobStore(session)
        product = AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session))
        deletion = ProjectDeletionJobAuthorizationService(
            PostgresProjectDeletionJobFactsReader(session)
        )
        recovery = JobRecoveryService(
            jobs,
            JobContinuationEligibilityService(
                jobs,
                product,
                ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
                supported_payloads=SUPPORTED,
                project_deletion_job_authorizer=deletion,
            ),
        )
        return await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            jobs,
            supported_payloads=SUPPORTED,
            worker_id=uuid4(),
            admitted_work_authorizer=product,
            job_recovery=recovery,
            lease_seconds=30,
            work_seconds=60,
        ).claim_next()


async def claim(database: Database) -> JobAttemptContextDTO:
    context = await claim_next(database)
    assert context is not None
    assert isinstance(context.binding, ProjectDeletionJobBindingDTO)
    return context


async def run_local(database: Database, context: JobAttemptContextDTO) -> None:
    async with database.session() as session:
        await ProjectDeletionShutdownService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            project_deletion_shutdown_writer=PostgresProjectDeletionShutdownWriter(session),
            project_deletion_job_authorizer=ProjectDeletionJobAuthorizationService(
                PostgresProjectDeletionJobFactsReader(session)
            ),
            job_store=PostgresJobStore(session),
            application_shutdown_effects_writer=PostgresProjectApplicationShutdownEffectsWriter(
                session
            ),
        ).shutdown(context)


async def assert_physical_pending(
    database: Database, context: JobAttemptContextDTO, *, terminal: str
) -> None:
    assert isinstance(context.binding, ProjectDeletionJobBindingDTO)
    async with database.session() as session:
        parent = await session.get(ProjectDeletionObligationRow, context.binding.obligation_id)
        job = await session.get(DurableJobRow, context.job_id.value)
        original = await session.get(IdempotencyReservationRow, context.binding.operation_id.value)
        assert parent is not None and job is not None
        assert (
            parent.shutdown_completed_at is not None
            and parent.physical_cleanup_completed_at is None
        )
        assert job.status == terminal and job.pending_effect is None
        assert original is None or original.expires_at is None
        pending = await PostgresProjectDeletionJobFactsReader(session).pending_physical(limit=1)
        assert len(pending) == 1
        assert (
            pending[0].binding == context.binding
            and pending[0].physical_cleanup_completed_at is None
        )


@pytest.mark.parametrize("missing_membership", [False, True])
async def test_real_handler_succeeds_child_without_completing_or_expiring_parent(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    deletion_scope: DeletionScenario,
    missing_membership: bool,
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    if missing_membership:
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == deletion_scope.defaults.project_id.value,
                    ProjectMembershipRow.principal_id == deletion_scope.account.principal_id.value,
                )
            )
    before_defaults: tuple[object, ...]
    async with database.session() as session:
        before_defaults = (
            tuple(
                await session.scalars(
                    select(ProjectUploadDefaultGroupRow.group_id).order_by(
                        ProjectUploadDefaultGroupRow.group_id
                    )
                )
            ),
            tuple(
                await session.scalars(
                    select(ProjectUploadDefaultResultRow.operation_id).order_by(
                        ProjectUploadDefaultResultRow.operation_id
                    )
                )
            ),
        )
    context = await claim(database)
    assert context.job_id == accepted.job_id
    operations = ApplicationWorkerOperations(
        database, JobSettings(work_seconds=60), asyncio.Event()
    )
    handler = ProjectDeletionJobHandler(operations)
    await handler.run(context, operations)
    await operations.succeed(context)
    await assert_physical_pending(database, context, terminal="succeeded")
    async with database.session() as session:
        key = await session.get(ApplicationKeyRow, deletion_scope.credential.key_id.value)
        principal = await session.get(PrincipalRow, deletion_scope.account.principal_id.value)
        actor = await session.get(
            PrincipalRow, deletion_scope.defaults.actor.access.actor_principal_id.value
        )
        assert key is not None and key.revoked_at is not None
        assert principal is not None and principal.status is PrincipalStatus.RETIRED
        assert actor is not None and actor.status is PrincipalStatus.ACTIVE
        assert (
            await session.get(
                ProjectMembershipRow, (deletion_scope.defaults.project_id.value, actor.id)
            )
            is not None
        )
        outside = await session.get(ProjectRow, deletion_scope.other_project.value)
        assert outside is not None and outside.status is ProjectStatus.ACTIVE
        assert set(
            await session.scalars(
                select(AccessGroupRow.id).where(
                    AccessGroupRow.project_id == deletion_scope.defaults.project_id.value
                )
            )
        ) == {g.group_id.value for g in deletion_scope.defaults.groups}
        assert before_defaults == (
            tuple(
                await session.scalars(
                    select(ProjectUploadDefaultGroupRow.group_id).order_by(
                        ProjectUploadDefaultGroupRow.group_id
                    )
                )
            ),
            tuple(
                await session.scalars(
                    select(ProjectUploadDefaultResultRow.operation_id).order_by(
                        ProjectUploadDefaultResultRow.operation_id
                    )
                )
            ),
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == deletion_scope.defaults.project_id.value
                )
            )
            == deletion_scope.revision + 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == accepted.operation.operation_id.value)
            )
            == 2
        )


async def test_committed_checkpoint_crash_recovers_without_repeating_effects(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    deletion_scope: DeletionScenario,
) -> None:
    await admit_deletion(database, deletion_scope)
    context = await claim(database)
    await run_local(database, context)
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(
                ProjectRow.id == deletion_scope.defaults.project_id.value
            )
        )
        events = tuple(await session.scalars(select(AccessAuditEventRow.id)))
    async with database.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == context.job_id.value)
            .values(lease_expires_at=now - timedelta(seconds=1))
        )
    assert await claim_next(database) is None
    await assert_physical_pending(database, context, terminal="succeeded")
    assert await claim_next(database) is None
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == deletion_scope.defaults.project_id.value
                )
            )
            == revision
        )
        assert tuple(await session.scalars(select(AccessAuditEventRow.id))) == events


@pytest.mark.parametrize("forged", [False, True], ids=["expired-fence", "foreign-fence"])
async def test_stale_or_foreign_fence_cannot_apply_application_effects(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    deletion_scope: DeletionScenario,
    forged: bool,
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    context = await claim(database)
    if forged:
        context = replace(context, fence=JobFence(uuid4()))
    else:
        async with database.session() as session, session.begin():
            now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
            assert now is not None
            await session.execute(
                update(DurableJobRow)
                .where(DurableJobRow.id == context.job_id.value)
                .values(lease_expires_at=now - timedelta(seconds=1))
            )
    with pytest.raises(JobFenceLostError):
        await run_local(database, context)
    async with database.session() as session:
        key = await session.get(ApplicationKeyRow, deletion_scope.credential.key_id.value)
        parent = await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
        assert key is not None and key.revoked_at is None
        assert parent is not None and parent.shutdown_completed_at is None


async def test_checkpoint_failure_rolls_back_real_revocations_and_revision(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    deletion_scope: DeletionScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    context = await claim(database)
    original = PostgresProjectDeletionShutdownWriter.record_shutdown

    async def fail_after_checkpoint(
        writer: PostgresProjectDeletionShutdownWriter,
        current: JobAttemptContextDTO,
        *,
        facts: ProjectDeletionShutdownFactsDTO,
        changed: bool,
        access_revision: int,
    ) -> None:
        await original(
            writer, current, facts=facts, changed=changed, access_revision=access_revision
        )
        raise ConnectionError("controlled lost checkpoint acknowledgment")

    monkeypatch.setattr(
        PostgresProjectDeletionShutdownWriter, "record_shutdown", fail_after_checkpoint
    )
    with pytest.raises(ConnectionError):
        await run_local(database, context)
    async with database.session() as session:
        parent = await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
        key = await session.get(ApplicationKeyRow, deletion_scope.credential.key_id.value)
        assert parent is not None and parent.shutdown_completed_at is None
        assert key is not None and key.revoked_at is None
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == deletion_scope.defaults.project_id.value
                )
            )
            == deletion_scope.revision + 1
        )


async def test_retained_original_continues_after_native_history_is_removed(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    deletion_scope: DeletionScenario,
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == accepted.operation.operation_id.value
            )
        )
    context = await claim(database)
    await run_local(database, context)
    operations = ApplicationWorkerOperations(
        database, JobSettings(work_seconds=60), asyncio.Event()
    )
    await operations.succeed(context)
    await assert_physical_pending(database, context, terminal="succeeded")


async def test_pending_scan_is_capped_deterministic_and_excludes_unfinished_local_work(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    deletion_scope: DeletionScenario,
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        assert await PostgresProjectDeletionJobFactsReader(session).pending_physical(limit=1) == ()
    context = await claim(database)
    await run_local(database, context)
    operations = ApplicationWorkerOperations(
        database, JobSettings(work_seconds=60), asyncio.Event()
    )
    await operations.succeed(context)
    async with database.session() as session:
        second = await deletion_service(session).delete(
            access=deletion_scope.defaults.actor.access,
            command=DeleteProjectCommand(deletion_scope.other_project, 1),
            context=deletion_context(deletion_scope.other_project, "second-pending"),
            request_id=RequestId(uuid4()),
        )
    second_context = await claim(database)
    assert second_context.job_id == second.job_id
    await run_local(database, second_context)
    async with database.session() as session, session.begin():
        reader = PostgresProjectDeletionJobFactsReader(session)
        first = await reader.pending_physical(limit=1)
        again = await reader.pending_physical(limit=1)
        both = await reader.pending_physical(limit=2)
        page_two = await reader.pending_physical(
            limit=1, after=(first[0].admitted_at, first[0].binding.obligation_id)
        )
        assert len(page_two) == 1
        assert page_two[0].binding.obligation_id == second.obligation_id.value
        assert first[0].physical_cleanup_completed_at is None
        assert len(first) == len(again) == 1 and len(both) == 2
        assert first[0].binding == again[0].binding == both[0].binding
        assert first[0].binding.obligation_id == accepted.obligation_id.value
        assert both[1].binding.obligation_id == second.obligation_id.value
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == deletion_scope.other_project.value
                )
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == second.operation.operation_id.value)
            )
            == 1
        )
        with pytest.raises(ValueError):
            await reader.pending_physical(limit=0)
        with pytest.raises(ValueError):
            await reader.pending_physical(limit=101)


async def test_registered_production_worker_releases_local_execution_without_parent_spin(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    deletion_scope: DeletionScenario,
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with application_worker_process(temporary_postgres_settings, artifact_cleanup=True):
        async with asyncio.timeout(10):
            while True:
                async with database.session() as session:
                    job = await session.get(DurableJobRow, accepted.job_id.value)
                    if job is not None and job.status == "succeeded":
                        assert job.attempt_count == 1
                        parent = await session.get(
                            ProjectDeletionObligationRow, accepted.obligation_id.value
                        )
                        assert parent is not None and parent.shutdown_completed_at is not None
                        assert parent.physical_cleanup_completed_at is None
                        break
                await asyncio.sleep(0.02)
    async with database.session() as session:
        row = await session.get(DurableJobRow, accepted.job_id.value)
        assert row is not None and row.status == "succeeded" and row.attempt_count == 1
        assert row.fence is None and row.lease_expires_at is None


async def test_exhausted_child_does_not_expire_or_complete_original_parent(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == accepted.job_id.value)
            .values(queued_deadline=now - timedelta(seconds=1))
        )
    assert await claim_next(database) is None
    async with database.session() as session:
        job = await session.get(DurableJobRow, accepted.job_id.value)
        parent = await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
        original = await session.get(
            IdempotencyReservationRow, accepted.operation.operation_id.value
        )
        assert job is not None and job.status == "failed"
        assert (
            parent is not None
            and parent.shutdown_completed_at is None
            and parent.physical_cleanup_completed_at is None
        )
        assert original is not None and original.expires_at is None
    assert await claim_next(database) is None


async def test_genuine_shutdown_history_survives_controlled_disposable_row_retirement(
    database: Database,
) -> None:
    """Retire only test-owned rows after genuine admission/shutdown, without claiming physical erasure."""
    creator = await seed_project_creator(database)
    target = (
        await create_project(database, creator, name="retention-target", key="retention-target")
    ).project
    async with database.session() as session:
        organization_revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == creator.organization_id.value
            )
        )
    assert organization_revision is not None
    outside = (
        await create_project(
            database,
            replace(creator, access_revision=organization_revision),
            name="retention-unrelated",
            key="retention-unrelated",
        )
    ).project
    async with database.session() as session:
        accepted = await deletion_service(session).delete(
            access=creator.access,
            command=DeleteProjectCommand(target.project_id, target.access_revision),
            context=deletion_context(target.project_id, "retire-history-original"),
            request_id=RequestId(uuid4()),
        )
    context = await claim(database)
    assert context.job_id == accepted.job_id
    await run_local(database, context)
    operations = ApplicationWorkerOperations(
        database, JobSettings(work_seconds=60), asyncio.Event()
    )
    await operations.succeed(context)
    async with database.session() as session:
        parent = await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
        child = await session.get(DurableJobRow, accepted.job_id.value)
        retained = await session.get(
            DeletionStatusBindingRow, accepted.operation.operation_id.value
        )
        assert parent is not None and parent.shutdown_completed_at is not None
        assert parent.physical_cleanup_completed_at is None
        assert child is not None and child.status == "succeeded"
        assert retained is not None
        original = (
            retained.request_id,
            retained.installation_id,
            retained.organization_id,
            retained.project_id,
            retained.initiator_principal_id,
            retained.method,
            retained.requested_route,
            retained.request_key,
            retained.request_fingerprint,
            retained.recorded_at,
            retained.retention_days,
            retained.retention_policy_version,
        )
        local_checkpoint = (parent.shutdown_completed_at, parent.source_revision)
    # Controlled storage retirement is not a Project erasure producer or a GC implementation.
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == accepted.operation.operation_id.value
            )
        )
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == target.project_id.value
            )
        )
        await session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.project_id == target.project_id.value
            )
        )
        await session.execute(
            delete(ProjectNameReservationRow).where(
                ProjectNameReservationRow.project_id == target.project_id.value
            )
        )
        await session.execute(delete(ProjectRow).where(ProjectRow.id == target.project_id.value))
        await session.execute(
            delete(DurableJobAttemptRow).where(DurableJobAttemptRow.job_id == accepted.job_id.value)
        )
        await session.execute(
            delete(DurableJobRow).where(DurableJobRow.id == accepted.job_id.value)
        )
    async with database.session() as session, session.begin():
        result = await DeletionStatusReadService(
            DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
            PostgresDeletionStatusReader(session),
        ).lookup(
            access=creator.access, query=GetDeletionStatusQuery(accepted.operation.operation_id)
        )
        assert isinstance(result, RetainedDeletionStatusDTO)
        assert result.operation_id == accepted.operation.operation_id
        assert result.job_status is None
        assert result.admission_confirmed is True and result.access_blocked is True
        assert (
            result.application_shutdown_complete is True
            and result.physical_cleanup_complete is False
        )
        assert result.expires_at is None
        retained = await session.get(
            DeletionStatusBindingRow, accepted.operation.operation_id.value
        )
        parent = await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
        assert retained is not None and parent is not None
        assert original == (
            retained.request_id,
            retained.installation_id,
            retained.organization_id,
            retained.project_id,
            retained.initiator_principal_id,
            retained.method,
            retained.requested_route,
            retained.request_key,
            retained.request_fingerprint,
            retained.recorded_at,
            retained.retention_days,
            retained.retention_policy_version,
        )
        assert local_checkpoint == (parent.shutdown_completed_at, parent.source_revision)
        assert parent.physical_cleanup_completed_at is None
        pending = await PostgresProjectDeletionJobFactsReader(session).pending_physical(limit=1)
        assert (
            len(pending) == 1 and pending[0].binding.operation_id == accepted.operation.operation_id
        )
        with pytest.raises(JobFenceLostError):
            await PostgresJobStore(session).require_current(context)
        assert await session.get(ProjectRow, target.project_id.value) is None
        assert await session.get(DurableJobRow, accepted.job_id.value) is None
        outside_row = await session.get(ProjectRow, outside.project_id.value)
        actor = await session.get(PrincipalRow, creator.access.actor_principal_id.value)
        assert outside_row is not None and outside_row.status is ProjectStatus.ACTIVE
        assert actor is not None and actor.status is PrincipalStatus.ACTIVE
        assert (
            await session.get(ProjectMembershipRow, (outside.project_id.value, actor.id))
            is not None
        )
