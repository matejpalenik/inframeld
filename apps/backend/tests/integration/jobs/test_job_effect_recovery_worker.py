"""Exercise the registered cleanup consumer with real SQL and private live-instance S3."""

import asyncio
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import timedelta
from io import BytesIO
from typing import Unpack
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3.type_defs import DeleteObjectOutputTypeDef, DeleteObjectRequestTypeDef
from sqlalchemy import func, literal, select, update
from tests.support.application_worker_process import application_worker_process
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    seed_artifact_scope,
)
from tests.support.seaweedfs_fixture import (
    BUCKET,
    SeaweedFixture,
    create_client,
    new_attempt,
    storage_settings,
)

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.bootstrap.application_worker_application_settings import (
    ApplicationWorkerApplicationSettings,
)
from inframeld_backend.bootstrap.application_worker_operations import ApplicationWorkerOperations
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.job_errors import SafeJobRetryError
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_job_handler import (
    ArtifactCleanupJobHandler,
)
from inframeld_backend.shared.application.services.job_continuation_eligibility_service import (
    JobContinuationEligibilityService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.services.job_recovery_service import JobRecoveryService
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_facts_reader import (
    PostgresArtifactCleanupFactsReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_effect_row import DurableJobEffectRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1"
    or os.getenv("INFRAMELD_RUN_ARTIFACT_INTEGRATION") != "1",
    reason="Requires the maintained private PostgreSQL and SeaweedFS services.",
)


@pytest.fixture(scope="module")
def seaweed() -> Iterator[SeaweedFixture]:
    with closing(create_client(bootstrap=True)) as bootstrap:
        try:
            bootstrap.create_bucket(Bucket=BUCKET)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
                raise
    yield SeaweedFixture()


async def _allocated(database: Database) -> ArtifactAllocationDTO:
    scope = await seed_artifact_scope(database)
    allocation = await allocate_artifact(database, artifact_scenario(scope), transfer_seconds=0.05)
    await asyncio.sleep(0.06)
    return allocation


async def _upload(seaweed: SeaweedFixture, allocation: ArtifactAllocationDTO) -> ArtifactAttemptDTO:
    body = seaweed.body(b"abandoned test bytes")
    original = allocation.reservation
    attempt = ArtifactAttemptDTO(
        original.artifact_id,
        original.attempt_id,
        original.scope,
        len(body),
        ArtifactContentDigest.from_content(body),
    )
    async with seaweed.open_store() as store:
        await store.put(attempt, BytesIO(body))
        assert await store.head(attempt.scope, attempt.attempt_id) is not None
    return attempt


async def _wait_status(database: Database, job_id: JobId, status: JobStatus) -> None:
    async with asyncio.timeout(10):
        while True:
            async with database.session() as session:
                row = await session.get(DurableJobRow, job_id.value)
                if row is not None and row.status == status.value:
                    return
            await asyncio.sleep(0.02)


async def _retained(
    database: Database, allocation: ArtifactAllocationDTO, *, attempts: int
) -> bytes:
    async with database.session() as session:
        job = await session.get(DurableJobRow, allocation.cleanup_job_id.value)
        obligation = await session.get(
            ArtifactCleanupObligationRow, allocation.cleanup_binding.obligation_id.value
        )
        target = await session.get(ArtifactAttemptRow, allocation.reservation.attempt_id.value)
        reservation = await session.get(
            ArtifactStagingReservationRow, allocation.reservation.reservation_id.value
        )
        assert (
            job is not None
            and obligation is not None
            and target is not None
            and reservation is not None
        )
        assert (
            job.status == JobStatus.RECOVERY_REQUIRED.value
            and job.reason == "physical_cleanup_pending"
        )
        assert job.attempt_count == attempts and job.pending_effect is None
        assert (
            obligation.execution_status == JobStatus.RECOVERY_REQUIRED.value
            and not obligation.physically_complete
        )
        assert not target.remote_removed and not target.published
        assert not reservation.released and not reservation.staging_removed
        assert (
            reservation.local_reserved_bytes
            == reservation.remote_reserved_bytes
            == reservation.limit_bytes
        )
        return job.checkpoint


def _settings(database: DatabaseSettings) -> ApplicationWorkerApplicationSettings:
    return ApplicationWorkerApplicationSettings(
        database=database,
        artifact_storage=storage_settings(),
        jobs=JobSettings(lease_seconds=30, database_timeout_seconds=1, work_seconds=60),
    )


async def _context(
    database: Database, settings: ApplicationWorkerApplicationSettings
) -> JobAttemptContextDTO:
    context = await _claim(database, settings)
    assert context is not None
    return context


async def _claim(
    database: Database, settings: ApplicationWorkerApplicationSettings
) -> JobAttemptContextDTO | None:
    async with (
        asyncio.timeout(settings.jobs.database_timeout_seconds),
        database.session() as session,
    ):
        jobs = PostgresJobStore(session)
        product = AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session))
        recovery = JobRecoveryService(
            jobs,
            JobContinuationEligibilityService(
                jobs,
                product,
                ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
                supported_payloads=(("artifact.cleanup", 1),),
            ),
        )
        return await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            jobs,
            worker_id=uuid4(),
            supported_payloads=(("artifact.cleanup", 1),),
            admitted_work_authorizer=product,
            job_recovery=recovery,
            lease_seconds=settings.jobs.lease_seconds,
            work_seconds=settings.jobs.work_seconds,
        ).claim_next()


@pytest.mark.asyncio
async def test_registered_worker_acknowledges_exact_delete_without_releasing_physical_obligation(
    database: Database, temporary_postgres_settings: DatabaseSettings, seaweed: SeaweedFixture
) -> None:
    allocation = await _allocated(database)
    original = await _upload(seaweed, allocation)
    control = new_attempt(b"retained control", scope=original.scope)
    async with seaweed.open_store() as store:
        await store.put(control, BytesIO(seaweed.body(b"retained control")))
        try:
            async with application_worker_process(
                temporary_postgres_settings, artifact_cleanup=True
            ):
                await _wait_status(database, allocation.cleanup_job_id, JobStatus.RECOVERY_REQUIRED)
            checkpoint = await _retained(database, allocation, attempts=1)
            assert (
                checkpoint
                == b"artifact.cleanup.delete-ack.v1\0"
                + allocation.cleanup_binding.obligation_id.value.bytes
                + original.artifact_id.value.bytes
                + original.attempt_id.value.bytes
            )
            assert await store.head(original.scope, original.attempt_id) is None
            assert await store.head(control.scope, control.attempt_id) is not None
        finally:
            await store.delete(control.scope, control.attempt_id)
            await store.delete(original.scope, original.attempt_id)


@pytest.mark.asyncio
async def test_actual_handler_abort_is_consumed_before_registered_worker_retries_original_target(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    seaweed: SeaweedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocation = await _allocated(database)
    original = await _upload(seaweed, allocation)
    context = await _context(database, _settings(temporary_postgres_settings))
    operations = ApplicationWorkerOperations(
        database, _settings(temporary_postgres_settings).jobs, asyncio.Event()
    )
    store = S3ArtifactStore(storage_settings(), effect_observation_recorder=operations)
    scheduled, release = asyncio.Event(), asyncio.Event()
    to_thread = asyncio.to_thread

    async def delayed(function: Callable[[], None]) -> None:
        scheduled.set()
        await release.wait()
        await to_thread(function)

    monkeypatch.setattr(asyncio, "to_thread", delayed)
    work = asyncio.create_task(
        ArtifactCleanupJobHandler(operations, store).run(context, operations)
    )
    try:
        await asyncio.wait_for(scheduled.wait(), 2)
        work.cancel()
        with pytest.raises(SafeJobRetryError):
            await work
    finally:
        release.set()
        try:
            await asyncio.wait_for(asyncio.gather(work, return_exceptions=True), 3)
        finally:
            try:
                await asyncio.wait_for(store.close(), 3)
            finally:
                monkeypatch.setattr(asyncio, "to_thread", to_thread)
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == context.job_id.value)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    async with application_worker_process(temporary_postgres_settings, artifact_cleanup=True):
        await _wait_status(database, context.job_id, JobStatus.QUEUED)
        async with database.session() as session, session.begin():
            proofs = tuple(
                await session.scalars(
                    select(DurableJobEffectRow).where(
                        DurableJobEffectRow.job_id == context.job_id.value
                    )
                )
            )
            assert (
                len(proofs) == 1
                and proofs[0].aborted_at is not None
                and proofs[0].consumed_at is not None
            )
            await session.execute(
                update(DurableJobRow)
                .where(DurableJobRow.id == context.job_id.value)
                .values(due_at=func.clock_timestamp())
            )
        await _wait_status(database, context.job_id, JobStatus.RECOVERY_REQUIRED)
    await _retained(database, allocation, attempts=2)
    async with database.session() as session:
        proofs = tuple(
            await session.scalars(
                select(DurableJobEffectRow).where(
                    DurableJobEffectRow.job_id == context.job_id.value
                )
            )
        )
        assert len(proofs) == 2 and sum(proof.admitted_at is not None for proof in proofs) == 2
    async with seaweed.open_store() as observed:
        assert await observed.head(original.scope, original.attempt_id) is None


@pytest.mark.asyncio
async def test_sql_pool_is_free_during_native_delete_and_committed_ack_prevents_redispatch(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    seaweed: SeaweedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocation = await _allocated(database)
    original = await _upload(seaweed, allocation)
    settings = _settings(
        temporary_postgres_settings.model_copy(
            update={"pool_size": 1, "max_overflow": 0, "pool_timeout_seconds": 0.2}
        )
    )
    owner = Database(settings.database)
    await owner.startup()
    operations = ApplicationWorkerOperations(owner, settings.jobs, asyncio.Event())
    client = create_client()
    native_delete = client.delete_object
    entered, release = threading.Event(), threading.Event()

    def delayed_delete(
        **arguments: Unpack[DeleteObjectRequestTypeDef],
    ) -> DeleteObjectOutputTypeDef:
        entered.set()
        assert release.wait(3), "The controlled native wait exceeded its test bound."
        return native_delete(**arguments)

    monkeypatch.setattr(client, "delete_object", delayed_delete)
    store = S3ArtifactStore(
        storage_settings(), client=client, effect_observation_recorder=operations
    )
    work: asyncio.Task[None] | None = None
    try:
        context = await _context(owner, settings)
        work = asyncio.create_task(
            ArtifactCleanupJobHandler(operations, store).run(context, operations)
        )
        assert await asyncio.to_thread(entered.wait, 1)
        async with asyncio.timeout(1), owner.session() as session:
            assert await session.scalar(select(literal(1))) == 1
        release.set()
        await asyncio.wait_for(work, 5)
    finally:
        release.set()
        try:
            if work is not None:
                await asyncio.wait_for(asyncio.gather(work, return_exceptions=True), 5)
        finally:
            try:
                await asyncio.wait_for(store.close(), 5)
            finally:
                await owner.shutdown()
    async with database.session() as session, session.begin():
        job = await session.get(DurableJobRow, allocation.cleanup_job_id.value)
        assert (
            job is not None
            and job.pending_effect is None
            and job.checkpoint.startswith(b"artifact.cleanup.delete-ack.v1\0")
        )
        # Controlled lease expiry retains the actual saved ACK and original budget.
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == allocation.cleanup_job_id.value)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    assert await _claim(database, _settings(temporary_postgres_settings)) is None
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == allocation.cleanup_job_id.value)
            .values(due_at=func.clock_timestamp())
        )
    async with application_worker_process(temporary_postgres_settings, artifact_cleanup=True):
        await _wait_status(database, allocation.cleanup_job_id, JobStatus.RECOVERY_REQUIRED)
    await _retained(database, allocation, attempts=2)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableJobEffectRow)
                .where(DurableJobEffectRow.job_id == allocation.cleanup_job_id.value)
            )
            == 1
        )
    async with seaweed.open_store() as observed:
        assert await observed.head(original.scope, original.attempt_id) is None
