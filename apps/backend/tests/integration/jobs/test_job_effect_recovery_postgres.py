"""Prove invocation persistence through actual allocation and the fenced job store."""

import asyncio
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import override
from uuid import uuid4

import boto3
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    seed_artifact_scope,
)

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.bootstrap.application_worker_operations import ApplicationWorkerOperations
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.enums.job_continuation_disposition import (
    JobContinuationDisposition,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    SafeJobRetryError,
)
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_effect_observation_recorder import (
    JobEffectObservationRecorder,
)
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_checkpoint_service import (
    ArtifactCleanupCheckpointService,
)
from inframeld_backend.shared.application.services.job_continuation_eligibility_service import (
    JobContinuationEligibilityService,
)
from inframeld_backend.shared.application.services.job_effect_observation_service import (
    JobEffectObservationService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.services.job_recovery_service import JobRecoveryService
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_facts_reader import (
    PostgresArtifactCleanupFactsReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_target_reader import (
    PostgresArtifactCleanupTargetReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_effect_row import DurableJobEffectRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_migration_creates_queryable_empty_invocation_history(database: Database) -> None:
    async with database.session() as session:
        assert tuple(await session.scalars(select(DurableJobEffectRow.id))) == ()


@pytest.mark.asyncio
async def test_registered_unsealed_cleanup_invocation_is_admitted_once(database: Database) -> None:
    scope = await seed_artifact_scope(database)
    scenario = artifact_scenario(scope)
    allocation = await allocate_artifact(database, scenario, transfer_seconds=0.05)
    await asyncio.sleep(0.06)
    async with database.session() as session:
        context = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("artifact.cleanup", 1),),
            worker_id=uuid4(),
            product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            recovery=_recovery_service(session),
        ).claim_next()
        assert context is not None and context.job_id == allocation.cleanup_job_id
        binding = JobEffectBindingDTO(
            JobEffectId(uuid4()),
            context,
            "delete-original",
            "delete",
            scenario.artifact_id,
            scenario.attempt_id,
            scope,
            None,
            None,
        )
        operation = JobEffectObservationService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
        )
        await operation.register(binding)
        await operation.admit_delete(binding.effect_id, scope, scenario.attempt_id)
        with pytest.raises(ConflictError):
            await operation.admit_delete(binding.effect_id, scope, scenario.attempt_id)
        async with session.begin():
            stored = await PostgresJobStore(session).effect(binding.effect_id)
            assert stored is not None and stored.admitted_at is not None
            assert stored.aborted_at is None and stored.consumed_at is None


def _recording_service(session: AsyncSession) -> JobEffectObservationService:
    return JobEffectObservationService(
        SqlAlchemyTransactionManager(session),
        PostgresJobStore(session),
        AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
        ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
    )


async def _cleanup_context(
    database: Database,
) -> tuple[ArtifactAllocationDTO, JobAttemptContextDTO]:
    scope = await seed_artifact_scope(database)
    scenario = artifact_scenario(scope)
    allocation = await allocate_artifact(database, scenario, transfer_seconds=0.05)
    await asyncio.sleep(0.06)
    async with database.session() as session:
        context = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("artifact.cleanup", 1),),
            worker_id=uuid4(),
            product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            recovery=_recovery_service(session),
        ).claim_next()
        assert context is not None and context.job_id == allocation.cleanup_job_id
        return allocation, context


async def _registered_invocation(
    database: Database, *, saved_checkpoint: bytes | None = None
) -> JobEffectBindingDTO:
    allocation, context = await _cleanup_context(database)
    async with database.session() as session:
        if saved_checkpoint is not None:
            checkpoints: JobCheckpoints = ArtifactCleanupCheckpointService(
                SqlAlchemyTransactionManager(session),
                PostgresJobStore(session),
                ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
            )
            await checkpoints.save(context, saved_checkpoint)
            assert context.checkpoint == b""
        binding = JobEffectBindingDTO(
            JobEffectId(uuid4()),
            context,
            "delete-original",
            "delete",
            allocation.reservation.artifact_id,
            allocation.reservation.attempt_id,
            allocation.reservation.scope,
            None,
            None,
        )
        await _recording_service(session).register(binding)
        return binding


@pytest.mark.asyncio
@pytest.mark.parametrize("sealed", [False, True])
async def test_preparation_commits_exact_locked_target_and_pending_invocation(
    database: Database,
    sealed: bool,
) -> None:
    allocation, context = await _cleanup_context(database)
    digest = ArtifactContentDigest.from_content(b"original sealed bytes")
    if sealed:
        async with database.session() as session, session.begin():
            await session.execute(
                update(ArtifactAttemptRow)
                .where(ArtifactAttemptRow.id == allocation.reservation.attempt_id.value)
                .values(length=21, digest=digest.value)
            )
    operations = ApplicationWorkerOperations(database, JobSettings(), asyncio.Event())
    prepared = await operations.prepare(replace(context, checkpoint=b"stale caller bytes"))
    assert prepared is not None and prepared.context.checkpoint == b""
    assert (prepared.artifact_id, prepared.artifact_attempt_id, prepared.scope) == (
        allocation.reservation.artifact_id,
        allocation.reservation.attempt_id,
        allocation.reservation.scope,
    )
    assert (prepared.length, prepared.digest) == ((21, digest) if sealed else (None, None))
    async with database.session() as session, session.begin():
        stored = await PostgresJobStore(session).effect(prepared.effect_id)
        job = await session.get(DurableJobRow, context.job_id.value)
        assert stored is not None and stored.binding == prepared and stored.admitted_at is None
        assert job is not None and job.pending_effect == prepared.unit
    with pytest.raises(ConflictError):
        await operations.prepare(context)


@pytest.mark.asyncio
async def test_authoritative_exact_saved_ack_suppresses_new_preparation(database: Database) -> None:
    allocation, context = await _cleanup_context(database)
    operations = ApplicationWorkerOperations(database, JobSettings(), asyncio.Event())
    prepared = await operations.prepare(context)
    assert prepared is not None
    acknowledgment = (
        b"artifact.cleanup.delete-ack.v1\0"
        + allocation.cleanup_binding.obligation_id.value.bytes
        + prepared.artifact_id.value.bytes
        + prepared.artifact_attempt_id.value.bytes
    )
    # This SQL case supplies the handler's controlled acknowledgment, without claiming a remote DELETE.
    await operations.confirm_effect(prepared.context, prepared.unit, acknowledgment)
    assert await operations.prepare(context) is None
    async with database.session() as session:
        ids = tuple(
            await session.scalars(
                select(DurableJobEffectRow.id).where(
                    DurableJobEffectRow.job_id == context.job_id.value
                )
            )
        )
        job = await session.get(DurableJobRow, context.job_id.value)
        assert ids == (prepared.effect_id.value,)
        assert job is not None and job.pending_effect is None and job.checkpoint == acknowledgment


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unknown-checkpoint", "foreign-ack", "expired-fence"])
async def test_preparation_rejection_leaves_no_pending_invocation(
    database: Database, failure: str
) -> None:
    allocation, context = await _cleanup_context(database)
    async with database.session() as session, session.begin():
        job = await session.get(DurableJobRow, context.job_id.value)
        assert job is not None
        if failure == "expired-fence":
            await session.execute(
                update(DurableJobRow)
                .where(DurableJobRow.id == context.job_id.value)
                .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
            )
        else:
            job.checkpoint = (
                b"unrecognized checkpoint"
                if failure == "unknown-checkpoint"
                else b"artifact.cleanup.delete-ack.v1\0"
                + uuid4().bytes
                + allocation.reservation.artifact_id.value.bytes
                + allocation.reservation.attempt_id.value.bytes
            )
    operations = ApplicationWorkerOperations(database, JobSettings(), asyncio.Event())
    with pytest.raises(JobFenceLostError if failure == "expired-fence" else ConflictError):
        await operations.prepare(context)
    async with database.session() as session:
        assert (
            tuple(
                await session.scalars(
                    select(DurableJobEffectRow.id).where(
                        DurableJobEffectRow.job_id == context.job_id.value
                    )
                )
            )
            == ()
        )
        job = await session.get(DurableJobRow, context.job_id.value)
        assert job is not None and job.pending_effect is None


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_scope", [False, True])
async def test_target_projection_requires_original_obligation_membership(
    database: Database,
    changed_scope: bool,
) -> None:
    allocation, _ = await _cleanup_context(database)
    foreign = await allocate_artifact(database, artifact_scenario(allocation.reservation.scope))
    binding = allocation.cleanup_binding
    if changed_scope:
        binding = replace(binding, scope=replace(binding.scope, project_id=ProjectId(uuid4())))
    async with database.session() as session, session.begin():
        reader = PostgresArtifactCleanupTargetReader(session)
        exact = await reader.read(allocation.cleanup_binding, allocation.reservation.attempt_id)
        assert exact is not None and exact.artifact_id == allocation.reservation.artifact_id
        assert (
            await reader.read(
                binding,
                allocation.reservation.attempt_id
                if changed_scope
                else foreign.reservation.attempt_id,
            )
            is None
        )


class _PostgresEffectRecorder(JobEffectObservationRecorder):
    """Join actual services with fresh sessions for this test, not production factory delivery."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def admit_put(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        async with self._database.session() as session:
            await _recording_service(session).admit_put(observation, attempt)

    @override
    async def admit_delete(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        async with self._database.session() as session:
            await _recording_service(session).admit_delete(observation, scope, attempt_id)

    @override
    async def record_put_abort(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        async with self._database.session() as session:
            await _recording_service(session).record_put_abort(observation, attempt)

    @override
    async def record_delete_abort(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        async with self._database.session() as session:
            await _recording_service(session).record_delete_abort(observation, scope, attempt_id)


@pytest.mark.asyncio
async def test_concurrent_sessions_admit_the_original_physical_invocation_once(
    database: Database,
) -> None:
    binding = await _registered_invocation(database)

    async def admit() -> bool:
        async with database.session() as session:
            try:
                await _recording_service(session).admit_delete(
                    binding.effect_id, binding.scope, binding.artifact_attempt_id
                )
            except ConflictError:
                return False
            return True

    assert sorted(await asyncio.gather(admit(), admit())) == [False, True]
    async with database.session() as session:
        with pytest.raises(ConflictError):
            await _recording_service(session).admit_delete(
                binding.effect_id, binding.scope, binding.artifact_attempt_id
            )


async def _produced_abort(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    saved_checkpoint: bytes | None = None,
) -> JobEffectBindingDTO:
    binding = await _registered_invocation(database, saved_checkpoint=saved_checkpoint)
    # No storage connection is made. The actual producer must exclude action entry.
    sdk = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url="https://storage.invalid",
        region_name="us-east-1",
        aws_access_key_id="fixture-access",
        aws_secret_access_key="fixture-secret",
    )
    sends: list[str] = []

    def unexpected_delete(**_values: object) -> None:
        sends.append("delete")
        raise AssertionError("The aborted callable must never enter the SDK action.")

    monkeypatch.setattr(sdk, "delete_object", unexpected_delete)
    scheduled, release = asyncio.Event(), asyncio.Event()
    original = asyncio.to_thread

    async def delayed(function: Callable[[], None]) -> None:
        scheduled.set()
        await release.wait()
        await original(function)

    monkeypatch.setattr(asyncio, "to_thread", delayed)
    store = S3ArtifactStore(
        ArtifactStorageSettings.model_validate(
            {
                "endpoint_url": "https://storage.invalid",
                "bucket": "private-artifacts",
                "access_key_id": "fixture-access",
                "secret_access_key": "fixture-secret",
            }
        ),
        client=sdk,
        observations=_PostgresEffectRecorder(database),
    )
    work = asyncio.create_task(
        store.delete(binding.scope, binding.artifact_attempt_id, observation=binding.effect_id)
    )
    try:
        await asyncio.wait_for(scheduled.wait(), 2)
        work.cancel()
        with pytest.raises(SafeJobRetryError):
            await work
        async with database.session() as session, session.begin():
            stored = await PostgresJobStore(session).effect(binding.effect_id)
            assert stored is not None and stored.aborted_at is not None
            assert stored.consumed_at is None
        with pytest.raises(ConflictError):
            await store.delete(
                binding.scope, binding.artifact_attempt_id, observation=binding.effect_id
            )
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)
        await asyncio.wait_for(store.close(), 2)
        monkeypatch.setattr(asyncio, "to_thread", original)
    assert sends == []
    return binding


@pytest.mark.asyncio
async def test_actual_adapter_abort_records_durable_proof_before_a_worker_trigger(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _produced_abort(database, tmp_path, monkeypatch)


@pytest.mark.asyncio
async def test_claim_requeues_exact_adapter_abort_in_the_original_transaction(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the still-missing production claim handoff with actual retained SQL proof."""
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    await _expired_original(database, binding)
    async with database.session() as session:
        jobs = PostgresJobStore(session)
        execution = JobExecutionService(
            SqlAlchemyTransactionManager(session),
            jobs,
            supported_payloads=(("artifact.cleanup", 1),),
            worker_id=uuid4(),
            product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            recovery=_recovery_service(session),
        )
        assert await execution.claim_next() is None
        async with session.begin():
            row = await session.get(DurableJobRow, binding.context.job_id.value)
            assert row is not None and row.status == JobStatus.QUEUED.value
            assert row.pending_effect is None and row.attempt_count == binding.context.attempt
            assert row.work_deadline == binding.context.work_deadline
            proof = await jobs.effect(binding.effect_id)
            assert proof is not None and proof.consumed_at is not None


async def _expired_original(database: Database, binding: JobEffectBindingDTO) -> JobSnapshotDTO:
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == binding.context.job_id.value)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
        job = await PostgresJobStore(session).next_candidate()
        assert job is not None and job.job_id == binding.context.job_id
        assert job.fence == binding.context.fence and job.attempt == binding.context.attempt
        assert job.lease_expires_at is not None and job.lease_expires_at <= job.observed_at
        return job


def _recovery_service(session: AsyncSession) -> JobRecoveryService:
    jobs = PostgresJobStore(session)
    return JobRecoveryService(
        jobs,
        JobContinuationEligibilityService(
            jobs,
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
            supported_payloads=(("artifact.cleanup", 1),),
        ),
    )


@pytest.mark.asyncio
async def test_historical_abort_recovery_consumes_once_without_a_live_old_fence(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    await _expired_original(database, binding)
    async with database.session() as session, session.begin():
        jobs = PostgresJobStore(session)
        job = await jobs.next_candidate()
        assert job is not None
        original = await jobs.effect(binding.effect_id)
        assert original is not None and original.aborted_at is not None
        with pytest.raises(JobFenceLostError):
            await jobs.require_current(binding.context)
        result = await _recovery_service(session).recover_in_transaction(job)
        assert result.disposition is JobContinuationDisposition.ELIGIBLE
        stored = await jobs.effect(binding.effect_id)
        assert stored is not None and stored.consumed_at is not None
        assert (stored.admitted_at, stored.aborted_at) == (
            original.admitted_at,
            original.aborted_at,
        )
        current = await session.get(DurableJobRow, job.job_id.value, populate_existing=True)
        assert current is not None and current.status == JobStatus.QUEUED.value
        assert current.pending_effect is None and current.attempt_count == job.attempt
        assert current.checkpoint == job.checkpoint and current.work_deadline == job.work_deadline
        ended = await session.scalar(
            select(DurableJobAttemptRow.ended_at).where(
                DurableJobAttemptRow.job_id == job.job_id.value,
                DurableJobAttemptRow.fence == binding.context.fence.value,
            )
        )
        assert ended is not None
    # Advance only the fixture's due time. The application/work budget is unchanged.
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == job.job_id.value)
            .values(due_at=func.clock_timestamp())
        )
    async with database.session() as session:
        replacement = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("artifact.cleanup", 1),),
            worker_id=uuid4(),
            product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            recovery=_recovery_service(session),
        ).claim_next()
        assert replacement is not None and replacement.job_id == binding.context.job_id
        assert replacement.attempt == binding.context.attempt + 1
        assert replacement.fence != binding.context.fence
        assert replacement.payload == binding.context.payload
        assert replacement.work_deadline == binding.context.work_deadline
        assert replacement.checkpoint == job.checkpoint
    async with database.session() as session, session.begin():
        with pytest.raises(JobFenceLostError):
            await PostgresJobStore(session).checkpoint(binding.context, b"stale", lease_seconds=30)
        with pytest.raises((ConflictError, JobFenceLostError)):
            await PostgresJobStore(session).consume_effect(job, original)
        stored = await PostgresJobStore(session).effect(binding.effect_id)
        assert stored is not None and stored.consumed_at is not None


@pytest.mark.asyncio
async def test_saved_checkpoint_with_unchanged_context_recovers_actual_adapter_abort_once(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = b"completed-cleanup-unit-1"
    binding = await _produced_abort(database, tmp_path, monkeypatch, saved_checkpoint=saved)
    assert binding.context.checkpoint == b""
    original = await _expired_original(database, binding)
    assert original.checkpoint == saved

    async with database.session() as session:
        claimed = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("artifact.cleanup", 1),),
            worker_id=uuid4(),
            product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            recovery=_recovery_service(session),
        ).claim_next()
        assert claimed is None
    async with database.session() as session, session.begin():
        proof = await PostgresJobStore(session).effect(binding.effect_id)
        current = await session.get(DurableJobRow, original.job_id.value)
        assert proof is not None and proof.consumed_at is not None
        consumed_at = proof.consumed_at
        assert proof.admitted_at is not None and proof.aborted_at is not None
        assert proof.binding.context.checkpoint == saved
        assert current is not None and current.status == JobStatus.QUEUED.value
        assert current.pending_effect is None and current.checkpoint == saved
        assert current.attempt_count == original.attempt
        assert current.payload == original.payload.data
        assert current.work_deadline == original.work_deadline
        assert current.queued_deadline == original.queued_deadline
        assert current.fence is None and current.due_at > proof.observed_at
        ended = await session.scalar(
            select(DurableJobAttemptRow.ended_at).where(
                DurableJobAttemptRow.job_id == original.job_id.value,
                DurableJobAttemptRow.fence == binding.context.fence.value,
            )
        )
        assert ended is not None

    # Polling before the retained backoff must neither consume again nor spend another attempt.
    async with database.session() as session:
        assert (
            await JobExecutionService(
                SqlAlchemyTransactionManager(session),
                PostgresJobStore(session),
                supported_payloads=(("artifact.cleanup", 1),),
                worker_id=uuid4(),
                product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                recovery=_recovery_service(session),
            ).claim_next()
            is None
        )
    async with database.session() as session, session.begin():
        proof = await PostgresJobStore(session).effect(binding.effect_id)
        current = await session.get(DurableJobRow, original.job_id.value)
        assert proof is not None and proof.consumed_at == consumed_at
        assert current is not None and current.status == JobStatus.QUEUED.value
        assert current.attempt_count == original.attempt and current.checkpoint == saved
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableJobEffectRow)
                .where(DurableJobEffectRow.job_id == original.job_id.value)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_changed_checkpoint_after_abort_requires_recovery_without_blocking_the_next_job(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    async with database.session() as session, session.begin():
        before = await PostgresJobStore(session).effect(binding.effect_id)
        fingerprint = await session.scalar(
            select(DurableJobEffectRow.binding_fingerprint).where(
                DurableJobEffectRow.id == binding.effect_id.value
            )
        )
        assert before is not None and before.aborted_at is not None and fingerprint is not None

    saved = b"confirmed-after-original-abort"
    async with database.session() as session:
        checkpoints: JobCheckpoints = ArtifactCleanupCheckpointService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
        )
        await checkpoints.save(binding.context, saved)
    assert binding.context.checkpoint == b""
    next_allocation = await allocate_artifact(
        database, artifact_scenario(binding.scope), transfer_seconds=0.05
    )
    await asyncio.sleep(0.06)
    original = await _expired_original(database, binding)
    assert original.checkpoint == saved

    async with database.session() as session:
        assert (
            await JobExecutionService(
                SqlAlchemyTransactionManager(session),
                PostgresJobStore(session),
                supported_payloads=(("artifact.cleanup", 1),),
                worker_id=uuid4(),
                product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                recovery=_recovery_service(session),
            ).claim_next()
            is None
        )
    async with database.session() as session, session.begin():
        current = await session.get(DurableJobRow, original.job_id.value)
        retained = await PostgresJobStore(session).effect(binding.effect_id)
        assert current is not None and current.status == JobStatus.RECOVERY_REQUIRED.value
        assert current.reason == "unknown_external_effect"
        assert current.pending_effect == binding.unit and current.checkpoint == saved
        assert current.attempt_count == original.attempt and current.fence is None
        assert current.payload == original.payload.data
        assert current.work_deadline == original.work_deadline
        assert current.queued_deadline == original.queued_deadline
        assert retained is not None and retained.consumed_at is None
        assert (retained.binding, retained.admitted_at, retained.aborted_at) == (
            before.binding,
            before.admitted_at,
            before.aborted_at,
        )
        assert (
            await session.scalar(
                select(DurableJobEffectRow.binding_fingerprint).where(
                    DurableJobEffectRow.id == binding.effect_id.value
                )
            )
            == fingerprint
        )

    async with database.session() as session:
        next_attempt = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("artifact.cleanup", 1),),
            worker_id=uuid4(),
            product=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            recovery=_recovery_service(session),
        ).claim_next()
        assert next_attempt is not None and next_attempt.job_id == next_allocation.cleanup_job_id
        assert next_attempt.binding == next_allocation.cleanup_binding
        assert next_attempt.attempt == 1 and next_attempt.fence != binding.context.fence
    async with database.session() as session, session.begin():
        retained = await PostgresJobStore(session).effect(binding.effect_id)
        assert retained is not None and retained.consumed_at is None
        current = await session.get(DurableJobRow, original.job_id.value)
        assert current is not None and current.status == JobStatus.RECOVERY_REQUIRED.value
        assert current.pending_effect == binding.unit and current.checkpoint == saved


@pytest.mark.asyncio
async def test_registration_replay_preserves_abort_and_rejects_a_later_checkpoint_boundary(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    async with database.session() as session, session.begin():
        before = await PostgresJobStore(session).effect(binding.effect_id)
        fingerprint = await session.scalar(
            select(DurableJobEffectRow.binding_fingerprint).where(
                DurableJobEffectRow.id == binding.effect_id.value
            )
        )
        assert before is not None and before.admitted_at is not None
        assert before.aborted_at is not None and before.consumed_at is None
        assert fingerprint is not None
    async with database.session() as session:
        await _recording_service(session).register(binding)
        with pytest.raises(ConflictError):
            await _recording_service(session).admit_delete(
                binding.effect_id, binding.scope, binding.artifact_attempt_id
            )
        async with session.begin():
            retained = await PostgresJobStore(session).effect(binding.effect_id)
            assert retained is not None and retained.consumed_at is None
            assert (retained.binding, retained.admitted_at, retained.aborted_at) == (
                before.binding,
                before.admitted_at,
                before.aborted_at,
            )
            assert (
                await session.scalar(
                    select(DurableJobEffectRow.binding_fingerprint).where(
                        DurableJobEffectRow.id == binding.effect_id.value
                    )
                )
                == fingerprint
            )

    saved = b"later-confirmed-progress"
    async with database.session() as session:
        checkpoints: JobCheckpoints = ArtifactCleanupCheckpointService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
        )
        await checkpoints.save(binding.context, saved)
        assert binding.context.checkpoint == b""
        with pytest.raises(ConflictError):
            await _recording_service(session).register(binding)
    async with database.session() as session, session.begin():
        retained = await PostgresJobStore(session).effect(binding.effect_id)
        assert retained is not None and retained.consumed_at is None
        assert (retained.binding, retained.admitted_at, retained.aborted_at) == (
            before.binding,
            before.admitted_at,
            before.aborted_at,
        )
        assert (
            await session.scalar(
                select(DurableJobEffectRow.binding_fingerprint).where(
                    DurableJobEffectRow.id == binding.effect_id.value
                )
            )
            == fingerprint
        )
        current = await session.get(DurableJobRow, binding.context.job_id.value)
        assert current is not None and current.status == JobStatus.RUNNING.value
        assert current.checkpoint == saved and current.pending_effect == binding.unit
        assert current.fence == binding.context.fence.value
        assert current.attempt_count == binding.context.attempt
        assert current.work_deadline == binding.context.work_deadline
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableJobEffectRow)
                .where(DurableJobEffectRow.job_id == binding.context.job_id.value)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_authoritative_lease_renewal_prevents_consumption_of_an_expired_snapshot(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    stale = await _expired_original(database, binding)
    # Model the authoritative state changing after observation, before recovery locks it.
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == stale.job_id.value)
            .values(lease_expires_at=func.clock_timestamp() + timedelta(seconds=30))
        )
    async with database.session() as session:
        with pytest.raises((JobFenceLostError, ConflictError)):
            async with session.begin():
                jobs = PostgresJobStore(session)
                original = await jobs.effect(binding.effect_id)
                assert original is not None
                await jobs.consume_effect(stale, original)
    async with database.session() as session, session.begin():
        stored = await PostgresJobStore(session).effect(binding.effect_id)
        assert stored is not None and stored.consumed_at is None
        current = await session.get(DurableJobRow, stale.job_id.value)
        assert current is not None and current.pending_effect == binding.unit
        assert current.status == JobStatus.RUNNING.value


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["payload", "proof-target", "cleanup-obligation"])
async def test_mismatched_historical_evidence_cannot_clear_original_pending_work(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mismatch: str
) -> None:
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    job = await _expired_original(database, binding)
    async with database.session() as session:
        with pytest.raises((ConflictError, JobFenceLostError)):
            async with session.begin():
                jobs = PostgresJobStore(session)
                original = await jobs.effect(binding.effect_id)
                assert original is not None
                reviewed = job
                if mismatch == "payload":
                    reviewed = replace(job, payload=JobPayload("artifact.cleanup", 1, b"different"))
                elif mismatch == "proof-target":
                    original = replace(
                        original,
                        binding=replace(
                            original.binding, artifact_attempt_id=ArtifactAttemptId(uuid4())
                        ),
                    )
                else:
                    assert isinstance(job.binding, ArtifactCleanupJobBindingDTO)
                    reviewed = replace(
                        job,
                        binding=replace(
                            job.binding, obligation_id=ArtifactCleanupObligationId(uuid4())
                        ),
                    )
                await jobs.consume_effect(reviewed, original)
    async with database.session() as session, session.begin():
        retained = await PostgresJobStore(session).effect(binding.effect_id)
        assert retained is not None and retained.consumed_at is None
        current = await session.get(DurableJobRow, job.job_id.value)
        assert current is not None and current.pending_effect == binding.unit
        assert current.checkpoint == job.checkpoint
        assert current.fence == binding.context.fence.value


@pytest.mark.asyncio
async def test_concurrent_recovery_consumes_the_original_abort_proof_once(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    expired = await _expired_original(database, binding)
    observed = asyncio.Barrier(2)

    async def consume() -> bool:
        async with database.session() as session:
            try:
                async with session.begin():
                    jobs = PostgresJobStore(session)
                    original = await jobs.effect(binding.effect_id)
                    assert original is not None
                    await asyncio.wait_for(observed.wait(), 2)
                    await jobs.consume_effect(expired, original)
            except (ConflictError, JobFenceLostError):
                return False
            return True

    outcomes = await asyncio.gather(consume(), consume(), return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
    assert outcomes.count(True) == 1 and outcomes.count(False) == 1
    async with database.session() as session, session.begin():
        jobs = PostgresJobStore(session)
        retained = await jobs.effect(binding.effect_id)
        assert retained is not None and retained.consumed_at is not None
        current = await session.get(DurableJobRow, binding.context.job_id.value)
        assert current is not None and current.pending_effect is None
        assert current.fence == binding.context.fence.value
        assert current.status == JobStatus.RUNNING.value


@pytest.mark.asyncio
async def test_failure_between_consumption_and_retirement_rolls_back_the_complete_transition(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = await _produced_abort(database, tmp_path, monkeypatch)
    await _expired_original(database, binding)
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="stop between consumption and retirement"):
            async with session.begin():
                jobs = PostgresJobStore(session)
                original = await jobs.next_candidate()
                observation = await jobs.effect(binding.effect_id)
                assert original is not None and observation is not None
                await jobs.consume_effect(original, observation)
                raise RuntimeError("stop between consumption and retirement")
    async with database.session() as session, session.begin():
        retained = await PostgresJobStore(session).effect(binding.effect_id)
        assert retained is not None and retained.consumed_at is None
        current = await session.get(DurableJobRow, binding.context.job_id.value)
        assert current is not None and current.pending_effect == binding.unit
        assert (
            current.fence == binding.context.fence.value
            and current.status == JobStatus.RUNNING.value
        )
        ended = await session.scalar(
            select(DurableJobAttemptRow.ended_at).where(
                DurableJobAttemptRow.job_id == current.id,
                DurableJobAttemptRow.fence == current.fence,
            )
        )
        assert ended is None


@pytest.mark.asyncio
async def test_candidate_peek_does_not_take_queue_or_job_ownership(database: Database) -> None:
    binding = await _registered_invocation(database)
    async with database.session() as owner, owner.begin():
        original = await PostgresJobStore(owner).next_candidate()
        assert original is not None and original.job_id == binding.context.job_id
        async with database.session() as observer, observer.begin():
            observed = await asyncio.wait_for(PostgresJobStore(observer).peek_candidate(), 1)
        assert observed is not None
        assert replace(observed, observed_at=original.observed_at) == original
        retained = await owner.get(DurableJobRow, original.job_id.value, populate_existing=True)
        assert retained is not None
        assert retained.fence == binding.context.fence.value
        assert retained.lease_expires_at == original.lease_expires_at
        assert retained.pending_effect == binding.unit
