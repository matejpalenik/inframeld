"""Keep cleanup execution identity and every terminal route outside product replay."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, func, select, update
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    completed_product_origin,
)

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.services.job_continuation_eligibility_service import (
    JobContinuationEligibilityService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.services.job_recovery_service import JobRecoveryService
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_facts_reader import (
    PostgresArtifactCleanupFactsReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "success",
        "failure",
        "unknown_effect",
        "queue_deadline",
        "work_deadline",
        "attempt_exhaustion",
        "unsupported",
    ],
)
async def test_cleanup_terminal_routes_preserve_original_business_job_and_replay(
    database: Database, route: str
) -> None:
    scope, origin = await completed_product_origin(database)
    async with database.session() as session:
        original = await session.get(IdempotencyReservationRow, origin.operation_id.value)
        assert original is not None
        before = (original.state, original.replay_kind, original.expires_at)
        original_job = await PostgresJobStore(session).find(origin.operation_id)
        assert original_job is not None and original_job.status is JobStatus.SUCCEEDED
    first = await allocate_artifact(database, artifact_scenario(scope, origin), transfer_seconds=2)
    second = await allocate_artifact(database, artifact_scenario(scope, origin), transfer_seconds=2)
    assert first.cleanup_job_id != second.cleanup_job_id
    assert first.cleanup_binding.obligation_id != second.cleanup_binding.obligation_id
    await asyncio.sleep(2.05)

    async with database.session() as session:
        jobs = PostgresJobStore(session)
        recovery_store = PostgresJobStore(session)
        product_authority = AdmittedWorkAuthorizationService(
            PostgresAdmittedWorkFactsReader(session)
        )
        recovery_service = JobRecoveryService(
            recovery_store,
            JobContinuationEligibilityService(
                recovery_store,
                product_authority,
                ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
                supported_payloads=() if route == "unsupported" else (("artifact.cleanup", 1),),
            ),
        )
        execution = JobExecutionService(
            SqlAlchemyTransactionManager(session),
            recovery_store,
            supported_payloads=() if route == "unsupported" else (("artifact.cleanup", 1),),
            worker_id=uuid4(),
            admitted_work_authorizer=product_authority,
            job_recovery=recovery_service,
        )
        if route == "queue_deadline":
            async with session.begin():
                await session.execute(
                    update(DurableJobRow)
                    .where(DurableJobRow.id == first.cleanup_job_id.value)
                    .values(queued_deadline=func.clock_timestamp() - timedelta(seconds=1))
                )
        context = await execution.claim_next()
        if route in ("queue_deadline", "unsupported"):
            assert context is None
        else:
            assert context is not None and context.job_id == first.cleanup_job_id
            if route in ("work_deadline", "attempt_exhaustion"):
                rounds = 1 if route == "work_deadline" else 3
                for number in range(1, rounds + 1):
                    assert context is not None and context.attempt == number
                    async with session.begin():
                        values = {"lease_expires_at": func.clock_timestamp() - timedelta(seconds=1)}
                        if route == "work_deadline":
                            values["work_deadline"] = func.clock_timestamp() - timedelta(seconds=1)
                        await session.execute(
                            update(DurableJobRow)
                            .where(DurableJobRow.id == first.cleanup_job_id.value)
                            .values(**values)
                        )
                    assert await execution.claim_next() is None
                    if number < rounds:
                        async with session.begin():
                            await session.execute(
                                update(DurableJobRow)
                                .where(DurableJobRow.id == first.cleanup_job_id.value)
                                .values(due_at=func.clock_timestamp(type_=DateTime(timezone=True)))
                            )
                        context = await execution.claim_next()
            else:
                async with session.begin():
                    if route == "unknown_effect":
                        await jobs.begin_effect(context, "delete-original-artifact")
                    await jobs.finish(
                        context,
                        status=JobStatus.FAILED if route == "failure" else JobStatus.SUCCEEDED,
                        reason="handler_failed" if route == "failure" else None,
                    )
    async with database.session() as session:
        original = await session.get(IdempotencyReservationRow, origin.operation_id.value)
        assert (
            original is not None
            and (original.state, original.replay_kind, original.expires_at) == before
        )
        found = await PostgresJobStore(session).find(origin.operation_id)
        assert (
            found is not None
            and found.job_id == original_job.job_id
            and found.status is JobStatus.SUCCEEDED
        )
        cleanup = await session.get(DurableJobRow, first.cleanup_job_id.value)
        obligation = await session.get(
            ArtifactCleanupObligationRow, first.cleanup_binding.obligation_id.value
        )
        assert cleanup is not None and cleanup.status not in (
            JobStatus.QUEUED.value,
            JobStatus.RUNNING.value,
        )
        assert obligation is not None and not obligation.physically_complete
        assert obligation.execution_status == cleanup.status
        assert (
            await session.scalar(
                select(DurableJobRow.id).where(DurableJobRow.id == second.cleanup_job_id.value)
            )
            == second.cleanup_job_id.value
        )
