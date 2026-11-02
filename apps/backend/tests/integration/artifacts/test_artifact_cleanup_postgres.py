"""Keep current cleanup ownership separate from revoked product authority."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    completed_product_origin,
)

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_checkpoint_service import (
    ArtifactCleanupCheckpointService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_facts_reader import (
    PostgresArtifactCleanupFactsReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


async def _claimed_cleanup(database: Database) -> JobAttemptContextDTO:
    scope, origin = await completed_product_origin(database)
    allocated = await allocate_artifact(
        database, artifact_scenario(scope, origin), transfer_seconds=2
    )
    await asyncio.sleep(2.05)
    async with database.session() as session:
        context = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("artifact.cleanup", 1),),
            worker_id=uuid4(),
        ).claim_next()
    assert context is not None and context.job_id == allocated.cleanup_job_id
    assert isinstance(context.binding, ArtifactCleanupJobBindingDTO)
    return context


def _checkpoints(session: AsyncSession) -> ArtifactCleanupCheckpointService:
    return ArtifactCleanupCheckpointService(
        SqlAlchemyTransactionManager(session),
        PostgresJobStore(session),
        ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
    )


@pytest.mark.asyncio
async def test_cleanup_checkpoint_survives_originating_principal_suspension_and_project_block(
    database: Database,
) -> None:
    context = await _claimed_cleanup(database)
    assert isinstance(context.binding, ArtifactCleanupJobBindingDTO)
    async with database.session() as session, session.begin():
        await session.execute(update(PrincipalRow).values(status=PrincipalStatus.SUSPENDED))
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == context.binding.scope.project_id.value)
            .values(status=ProjectStatus.DELETING)
        )
    async with database.session() as session:
        await _checkpoints(session).save(context, b"confirmed cleanup progress")
    async with database.session() as session:
        job = await session.get(DurableJobRow, context.job_id.value)
        assert job is not None and job.checkpoint == b"confirmed cleanup progress"
        assert job.status == JobStatus.RUNNING.value


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["obligation", "scope", "request"])
async def test_changed_cleanup_context_cannot_save_progress(
    database: Database, changed: str
) -> None:
    context = await _claimed_cleanup(database)
    assert isinstance(context.binding, ArtifactCleanupJobBindingDTO)
    binding = context.binding
    if changed == "obligation":
        binding = replace(binding, obligation_id=ArtifactCleanupObligationId(uuid4()))
    elif changed == "scope":
        binding = replace(binding, scope=replace(binding.scope, project_id=ProjectId(uuid4())))
    else:
        binding = replace(binding, origin=replace(binding.origin, request_id=RequestId(uuid4())))
    async with database.session() as session:
        with pytest.raises(JobFenceLostError):
            await _checkpoints(session).save(replace(context, binding=binding), b"forged progress")
    async with database.session() as session:
        job = await session.get(DurableJobRow, context.job_id.value)
        assert job is not None and job.checkpoint == b"" and job.status == JobStatus.RUNNING.value


@pytest.mark.asyncio
async def test_cleanup_lost_target_ownership_denies_protected_progress(database: Database) -> None:
    context = await _claimed_cleanup(database)
    assert isinstance(context.binding, ArtifactCleanupJobBindingDTO)
    async with database.session() as session, session.begin():
        await session.execute(update(ArtifactAttemptRow).values(project_id=uuid4()))
    async with database.session() as session:
        with pytest.raises((AccessDeniedError, JobStoppedError)):
            await _checkpoints(session).save(context, b"unsafe progress")
    async with database.session() as session:
        job = await session.get(DurableJobRow, context.job_id.value)
        assert job is not None and job.checkpoint == b""


@pytest.mark.asyncio
async def test_incomplete_cleanup_cannot_report_success_or_release_obligation(
    database: Database,
) -> None:
    context = await _claimed_cleanup(database)
    assert isinstance(context.binding, ArtifactCleanupJobBindingDTO)
    async with database.session() as session:
        with pytest.raises(JobStoppedError):
            await _checkpoints(session).succeed(context)
    async with database.session() as session:
        job = await session.get(DurableJobRow, context.job_id.value)
        obligation = await session.get(
            ArtifactCleanupObligationRow, context.binding.obligation_id.value
        )
        assert job is not None and job.status == JobStatus.RECOVERY_REQUIRED.value
        assert obligation is not None and not obligation.physically_complete


@pytest.mark.asyncio
async def test_product_cancellation_cannot_cancel_original_cleanup_obligation(
    database: Database,
) -> None:
    scope, origin = await completed_product_origin(database)
    allocated = await allocate_artifact(database, artifact_scenario(scope, origin))
    async with database.session() as session, session.begin():
        await PostgresJobStore(session).request_cancel(allocated.cleanup_job_id)
    async with database.session() as session:
        job = await session.get(DurableJobRow, allocated.cleanup_job_id.value)
        assert job is not None and not job.cancel_requested
        obligation = await session.get(
            ArtifactCleanupObligationRow, allocated.cleanup_binding.obligation_id.value
        )
        assert obligation is not None and not obligation.physically_complete
