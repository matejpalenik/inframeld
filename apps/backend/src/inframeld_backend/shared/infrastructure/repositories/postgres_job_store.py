import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID, uuid4

from sqlalchemy import DateTime, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.dtos.job_effect_observation_dto import (
    JobEffectObservationDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.enums.job_effect_observation_kind import (
    JobEffectObservationKind,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobQueueFullError,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_effect_row import DurableJobEffectRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresJobStore(JobStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def register_effect(self, binding: JobEffectBindingDTO) -> None:
        row, _ = await self._owned_row(binding.context)
        if row.work_deadline != binding.context.work_deadline:
            raise JobFenceLostError("The original work deadline changed.")
        # Retain durable progress without mutating the handler's immutable resume context.
        binding = replace(binding, context=replace(binding.context, checkpoint=row.checkpoint))
        self._require_checkpoint(binding.context.checkpoint)
        await self.validate_effect_target(binding)
        existing = await self.effect(binding.effect_id)
        if existing is not None:
            if existing.binding != binding or row.pending_effect != binding.unit:
                raise ConflictError("Invocation identity already belongs to other original work.")
            return
        if row.pending_effect is not None:
            raise ConflictError("An original physical invocation is still unresolved.")
        if (
            not binding.unit
            or len(binding.unit) > 100
            or binding.action not in (JobEffectAction.PUT, JobEffectAction.DELETE)
        ):
            raise ConflictError("The original physical invocation is unsupported.")
        row.pending_effect = binding.unit
        self._session.add(
            DurableJobEffectRow(
                id=binding.effect_id.value,
                job_id=binding.context.job_id.value,
                attempt=binding.context.attempt,
                fence=binding.context.fence.value,
                unit=binding.unit,
                action=binding.action,
                binding_fingerprint=self._effect_fingerprint(binding),
                artifact_id=binding.artifact_id.value,
                artifact_attempt_id=binding.artifact_attempt_id.value,
                installation_id=binding.scope.installation_id.value,
                organization_id=binding.scope.organization_id.value,
                project_id=binding.scope.project_id.value,
                work_deadline=binding.context.work_deadline,
                checkpoint=binding.context.checkpoint,
                length=binding.length,
                digest=binding.digest.value if binding.digest is not None else None,
            )
        )
        await self._session.flush()

    @override
    async def effect(self, effect_id: JobEffectId) -> JobEffectObservationDTO | None:
        self._require_transaction()
        row = await self._session.scalar(
            select(DurableJobEffectRow)
            .where(DurableJobEffectRow.id == effect_id.value)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        original = await self._session.get(DurableJobRow, row.job_id, populate_existing=True)
        if original is None or row.action not in (JobEffectAction.PUT, JobEffectAction.DELETE):
            raise ConflictError("The original invocation binding is unavailable.")
        now = await self._now()
        job = await self._snapshot(original, now)
        context = JobAttemptContextDTO(
            job_id=job.job_id,
            binding=job.binding,
            payload=job.payload,
            attempt=row.attempt,
            fence=JobFence(row.fence),
            work_deadline=row.work_deadline,
            checkpoint=row.checkpoint,
        )
        binding = JobEffectBindingDTO(
            effect_id=effect_id,
            context=context,
            unit=row.unit,
            action=JobEffectAction(row.action),
            artifact_id=ArtifactId(row.artifact_id),
            artifact_attempt_id=ArtifactAttemptId(row.artifact_attempt_id),
            scope=ArtifactScopeDTO(
                InstallationId(row.installation_id),
                OrganizationId(row.organization_id),
                ProjectId(row.project_id),
            ),
            length=row.length,
            digest=ArtifactContentDigest(row.digest) if row.digest is not None else None,
        )
        if self._effect_fingerprint(binding) != row.binding_fingerprint:
            raise ConflictError("The retained invocation no longer matches its original work.")
        return JobEffectObservationDTO(
            binding=binding,
            observed_at=now,
            admitted_at=row.admitted_at,
            kind=JobEffectObservationKind.NOT_DISPATCHED if row.aborted_at is not None else None,
            aborted_at=row.aborted_at,
            consumed_at=row.consumed_at,
        )

    @override
    async def validate_effect_target(self, binding: JobEffectBindingDTO) -> None:
        self._require_transaction()
        target = await self._session.scalar(
            select(ArtifactAttemptRow)
            .where(ArtifactAttemptRow.id == binding.artifact_attempt_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if target is None or (
            target.artifact_id,
            target.installation_id,
            target.organization_id,
            target.project_id,
            target.length,
            target.digest,
        ) != (
            binding.artifact_id.value,
            binding.scope.installation_id.value,
            binding.scope.organization_id.value,
            binding.scope.project_id.value,
            binding.length,
            binding.digest.value if binding.digest is not None else None,
        ):
            raise ConflictError("The original artifact target or sealed expectation changed.")
        if binding.action == JobEffectAction.PUT and (
            binding.length is None or binding.digest is None or target.retired
        ):
            raise ConflictError("The original PUT has no usable sealed expectation.")
        if binding.action == JobEffectAction.DELETE and (target.published or target.put_pending):
            raise ConflictError(
                "The original target still requires publication or write reconciliation."
            )

    @override
    async def admit_effect(self, observation: JobEffectObservationDTO) -> None:
        binding = observation.binding
        job, now = await self._owned_row(binding.context)
        if job.pending_effect != binding.unit or job.work_deadline != binding.context.work_deadline:
            raise ConflictError("The invocation no longer matches its original pending work.")
        await self.validate_effect_target(binding)
        claimed = await self._session.scalar(
            update(DurableJobEffectRow)
            .where(
                DurableJobEffectRow.id == binding.effect_id.value,
                DurableJobEffectRow.job_id == binding.context.job_id.value,
                DurableJobEffectRow.attempt == binding.context.attempt,
                DurableJobEffectRow.fence == binding.context.fence.value,
                DurableJobEffectRow.unit == binding.unit,
                DurableJobEffectRow.binding_fingerprint == self._effect_fingerprint(binding),
                DurableJobEffectRow.admitted_at.is_(None),
                DurableJobEffectRow.aborted_at.is_(None),
                DurableJobEffectRow.consumed_at.is_(None),
            )
            .values(admitted_at=now)
            .returning(DurableJobEffectRow.id)
        )
        if claimed is None:
            raise ConflictError("Physical invocation admission cannot be replayed.")
        await self._session.flush()

    @staticmethod
    def _effect_fingerprint(binding: JobEffectBindingDTO) -> bytes:
        """Bind exact typed meaning without using mutable job state as replacement input."""
        context = binding.context
        parts = [
            b"inframeld-job-effect-v1",
            binding.effect_id.value.bytes,
            context.job_id.value.bytes,
            str(context.attempt).encode(),
            context.fence.value.bytes,
            binding.unit.encode(),
            binding.action.encode(),
            context.payload.kind.encode(),
            str(context.payload.version).encode(),
            context.payload.data,
            context.checkpoint,
            context.work_deadline.astimezone(UTC).isoformat().encode(),
            binding.artifact_id.value.bytes,
            binding.artifact_attempt_id.value.bytes,
            binding.scope.installation_id.value.bytes,
            binding.scope.organization_id.value.bytes,
            binding.scope.project_id.value.bytes,
            str(binding.length).encode(),
            binding.digest.value if binding.digest is not None else b"",
        ]
        original = context.binding
        if isinstance(original, ProductJobBindingDTO):
            authority = original.authority
            parts.extend(
                [
                    b"product",
                    original.operation_id.value.encode(),
                    original.request_id.value.bytes,
                    authority.principal_id.value.bytes,
                    authority.principal_kind.value.encode(),
                    authority.installation_id.value.bytes,
                    authority.organization_id.value.bytes,
                    authority.project_id.value.bytes,
                    authority.action_id.value.encode(),
                ]
            )
            human = authority.human_binding
            if human is None:
                parts.append(b"no-human-binding")
            else:
                parts.extend(
                    [
                        b"human",
                        human.identity.authority.value.encode(),
                        human.identity.subject.value.encode(),
                        human.installation_id.value.bytes,
                        str(human.version.value).encode(),
                    ]
                )
        else:
            parts.extend(
                [
                    b"cleanup",
                    original.obligation_id.value.bytes,
                    original.kind.value.encode(),
                    original.scope.installation_id.value.bytes,
                    original.scope.organization_id.value.bytes,
                    original.scope.project_id.value.bytes,
                    original.origin.request_id.value.bytes,
                ]
            )
            origin = original.origin
            if isinstance(origin, BusinessOperationArtifactOriginDTO):
                parts.extend([b"business", origin.operation_id.value.encode()])
            else:
                parts.extend([b"unadmitted-staging", origin.attempt_id.value.bytes])
        digest = hashlib.sha256()
        for part in parts:
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
        return digest.digest()

    @override
    async def record_effect_abort(self, observation: JobEffectObservationDTO) -> None:
        binding = observation.binding
        job, now = await self._owned_row(binding.context)
        if (
            job.pending_effect != binding.unit
            or job.work_deadline != binding.context.work_deadline
            or observation.admitted_at is None
            or observation.consumed_at is not None
        ):
            raise ConflictError("The original invocation has no live recording admission.")
        await self.validate_effect_target(binding)
        recorded = await self._session.scalar(
            update(DurableJobEffectRow)
            .where(
                DurableJobEffectRow.id == binding.effect_id.value,
                DurableJobEffectRow.job_id == binding.context.job_id.value,
                DurableJobEffectRow.attempt == binding.context.attempt,
                DurableJobEffectRow.fence == binding.context.fence.value,
                DurableJobEffectRow.unit == binding.unit,
                DurableJobEffectRow.binding_fingerprint == self._effect_fingerprint(binding),
                DurableJobEffectRow.admitted_at == observation.admitted_at,
                DurableJobEffectRow.admitted_at <= now,
                DurableJobEffectRow.aborted_at.is_(None),
                DurableJobEffectRow.consumed_at.is_(None),
            )
            .values(aborted_at=now)
            .returning(DurableJobEffectRow.id)
        )
        if recorded is None:
            raise ConflictError("The original admitted invocation cannot record abort proof.")
        await self._session.flush()

    @override
    async def pending_observation(self, job: JobSnapshotDTO) -> JobEffectObservationDTO | None:
        row, _ = await self._expired_effect_job(job)
        if row.pending_effect is None:
            return None
        candidates = tuple(
            await self._session.scalars(
                select(DurableJobEffectRow.id)
                .where(
                    DurableJobEffectRow.job_id == row.id,
                    DurableJobEffectRow.attempt == row.attempt_count,
                    DurableJobEffectRow.fence == row.fence,
                    DurableJobEffectRow.unit == row.pending_effect,
                    DurableJobEffectRow.admitted_at.is_not(None),
                    DurableJobEffectRow.aborted_at.is_not(None),
                    DurableJobEffectRow.consumed_at.is_(None),
                )
                .limit(2)
            )
        )
        if len(candidates) != 1:
            return None
        try:
            return await self.effect(JobEffectId(candidates[0]))
        except ConflictError:
            return None

    @override
    async def consume_effect(
        self, job: JobSnapshotDTO, observation: JobEffectObservationDTO
    ) -> None:
        row, now = await self._expired_effect_job(job)
        binding = observation.binding
        context = binding.context
        if (
            observation.kind is not JobEffectObservationKind.NOT_DISPATCHED
            or observation.admitted_at is None
            or observation.aborted_at is None
            or not observation.admitted_at
            <= observation.aborted_at
            <= observation.observed_at
            <= now
            or observation.consumed_at is not None
            or (
                context.job_id,
                context.binding,
                context.payload,
                context.attempt,
                context.fence,
                context.work_deadline,
                context.checkpoint,
                binding.unit,
            )
            != (
                job.job_id,
                job.binding,
                job.payload,
                job.attempt,
                job.fence,
                job.work_deadline,
                job.checkpoint,
                row.pending_effect,
            )
        ):
            raise ConflictError("Historical proof does not match the original pending work.")
        if isinstance(context.binding, ArtifactCleanupJobBindingDTO):
            target = await self._session.scalar(
                select(ArtifactCleanupTargetRow.attempt_id)
                .where(
                    ArtifactCleanupTargetRow.obligation_id == context.binding.obligation_id.value,
                    ArtifactCleanupTargetRow.attempt_id == binding.artifact_attempt_id.value,
                )
                .with_for_update()
            )
            if target is None or binding.scope != context.binding.scope:
                raise ConflictError("Historical proof is outside the original cleanup targets.")
        await self.validate_effect_target(binding)
        retained = await self.effect(binding.effect_id)
        if retained is None or (
            retained.binding,
            retained.admitted_at,
            retained.aborted_at,
            retained.consumed_at,
        ) != (binding, observation.admitted_at, observation.aborted_at, None):
            raise ConflictError("The exact committed historical proof is unavailable.")

        consumed = await self._session.scalar(
            update(DurableJobEffectRow)
            .where(
                DurableJobEffectRow.id == binding.effect_id.value,
                DurableJobEffectRow.job_id == row.id,
                DurableJobEffectRow.attempt == row.attempt_count,
                DurableJobEffectRow.fence == row.fence,
                DurableJobEffectRow.unit == row.pending_effect,
                DurableJobEffectRow.binding_fingerprint == self._effect_fingerprint(binding),
                DurableJobEffectRow.admitted_at == observation.admitted_at,
                DurableJobEffectRow.aborted_at == observation.aborted_at,
                DurableJobEffectRow.consumed_at.is_(None),
            )
            .values(consumed_at=now)
            .returning(DurableJobEffectRow.id)
        )
        if consumed is None:
            raise ConflictError("Historical proof cannot be consumed more than once.")
        row.pending_effect = None
        await self._session.flush()

    @override
    async def peek_candidate(self) -> JobSnapshotDTO | None:
        return await self._candidate(lock=False)

    async def _candidate(self, *, lock: bool) -> JobSnapshotDTO | None:
        """Observe the next running or due job, optionally locking it for queue coordination."""
        self._require_transaction()
        now = await self._now()
        query = (
            select(DurableJobRow)
            .where(
                or_(
                    DurableJobRow.status == JobStatus.RUNNING.value,
                    (DurableJobRow.status == JobStatus.QUEUED.value)
                    & or_(DurableJobRow.due_at <= now, DurableJobRow.queued_deadline <= now),
                )
            )
            .order_by(
                case((DurableJobRow.status == JobStatus.RUNNING.value, 0), else_=1),
                DurableJobRow.admitted_at,
                DurableJobRow.id,
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        row = await self._session.scalar(query)
        return None if row is None else await self._snapshot(row, now)

    async def _expired_effect_job(self, job: JobSnapshotDTO) -> tuple[DurableJobRow, datetime]:
        """Lock the observed expired attempt without reviving its former ownership."""
        await self._queue_turn()
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(DurableJobRow.id == job.job_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = await self._now()
        if (
            row is None
            or job.status is not JobStatus.RUNNING
            or job.fence is None
            or job.lease_expires_at is None
            or job.lease_expires_at > job.observed_at
            or row.status != job.status.value
            or row.attempt_count != job.attempt
            or row.fence != job.fence.value
            or row.lease_expires_at is None
            or row.lease_expires_at != job.lease_expires_at
            or row.lease_expires_at > now
        ):
            raise JobFenceLostError("The observed expired attempt is no longer available.")
        if row.binding_kind == "artifact_cleanup":
            obligation = await self._session.scalar(
                select(ArtifactCleanupObligationRow)
                .where(ArtifactCleanupObligationRow.id == row.cleanup_obligation_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if obligation is None:
                raise ConflictError("The original cleanup obligation is unavailable.")
        current = await self._snapshot(row, now)
        if (
            current.binding,
            current.payload,
            current.work_deadline,
            current.checkpoint,
            current.pending_effect,
            current.cancel_requested,
        ) != (
            job.binding,
            job.payload,
            job.work_deadline,
            job.checkpoint,
            job.pending_effect,
            job.cancel_requested,
        ):
            raise JobFenceLostError("The observed original pending work changed.")
        return row, now

    @override
    async def admit(
        self,
        *,
        operation_id: OperationId,
        request_id: RequestId,
        authority: AdmittedWorkAuthorityDTO,
        payload: JobPayload,
        capacity: int,
    ) -> JobAdmissionDTO:
        if not self._session.in_transaction():
            raise RuntimeError("Job admission requires its caller-owned transaction.")
        if not 1 <= capacity <= 8:
            raise ValueError("Ordinary job capacity must be between one and eight.")
        queue = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if queue is None:
            raise RuntimeError("The ordinary job queue is not initialized.")

        reservation = await self._session.scalar(
            select(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == operation_id.value
            )
        )
        if reservation is None or (
            reservation.state is not OperationReservationState.IN_PROGRESS
            or reservation.principal_id != authority.principal_id.value
            or reservation.organization_id != authority.organization_id.value
            or reservation.project_id != authority.project_id.value
        ):
            raise ConflictError("Job admission requires its original checked reservation.")
        count = await self._session.scalar(
            select(func.count())
            .select_from(DurableJobRow)
            .where(DurableJobRow.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)))
        )
        if count is None or count >= capacity:
            raise JobQueueFullError("The ordinary job queue is full.")
        now = await self._session.scalar(select(func.clock_timestamp()))
        if now is None:
            raise RuntimeError("The database clock is unavailable.")
        job_id = JobId(uuid4())
        binding = authority.human_binding
        self._session.add(
            DurableJobRow(
                id=job_id.value,
                operation_id=operation_id.value,
                request_id=request_id.value,
                installation_id=authority.installation_id.value,
                principal_id=authority.principal_id.value,
                principal_kind=authority.principal_kind.value,
                organization_id=authority.organization_id.value,
                project_id=authority.project_id.value,
                action_id=authority.action_id.value,
                payload_kind=payload.kind,
                payload_version=payload.version,
                payload=payload.data,
                admitted_at=now,
                queued_deadline=now + timedelta(hours=24),
                due_at=now,
                human_authority=binding.identity.authority.value if binding is not None else None,
                human_subject=binding.identity.subject.value if binding is not None else None,
                human_version=binding.version.value if binding is not None else None,
            )
        )
        await self._session.flush()
        return JobAdmissionDTO(job_id, operation_id, True)

    @override
    async def find(self, operation_id: OperationId) -> JobSnapshotDTO | None:
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(
                DurableJobRow.operation_id == operation_id.value,
                DurableJobRow.binding_kind == "product",
            )
            .execution_options(populate_existing=True)
        )
        return None if row is None else await self._snapshot(row, await self._now())

    @override
    async def next_candidate(self) -> JobSnapshotDTO | None:
        await self._queue_turn()
        return await self._candidate(lock=True)

    @override
    async def start_attempt(
        self, job: JobSnapshotDTO, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO:
        await self._queue_turn()
        if not 0 < lease_seconds <= 120 or not 0 < work_seconds <= 7200:
            raise ValueError("The ordinary attempt budget is outside its finite bounds.")
        now = await self._now()
        active = await self._session.scalar(
            select(func.count())
            .select_from(DurableJobRow)
            .where(DurableJobRow.status == JobStatus.RUNNING.value)
        )
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(DurableJobRow.id == job.job_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            active
            or row is None
            or row.status != JobStatus.QUEUED.value
            or row.cancel_requested
            or row.due_at > now
            or row.queued_deadline <= now
            or row.attempt_count >= 3
        ):
            raise ConflictError("The job is not eligible for a new attempt.")
        deadline = row.work_deadline or now + timedelta(seconds=work_seconds)
        if deadline <= now:
            raise ConflictError("The original job work deadline has expired.")
        fence = JobFence(uuid4())
        row.status = JobStatus.RUNNING.value
        row.attempt_count += 1
        row.fence = fence.value
        row.worker_id = worker_id
        row.work_deadline = deadline
        row.lease_expires_at = min(now + timedelta(seconds=lease_seconds), deadline)
        self._session.add(
            DurableJobAttemptRow(
                job_id=row.id,
                number=row.attempt_count,
                fence=fence.value,
                worker_id=worker_id,
                started_at=now,
            )
        )
        await self._session.flush()
        saved = await self._snapshot(row, now)
        return JobAttemptContextDTO(
            job_id=saved.job_id,
            binding=saved.binding,
            payload=saved.payload,
            attempt=saved.attempt,
            fence=fence,
            work_deadline=deadline,
            checkpoint=saved.checkpoint,
        )

    @override
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO:
        row, now = await self._owned_row(context)
        return await self._snapshot(row, now)

    @override
    async def checkpoint(
        self, context: JobAttemptContextDTO, data: bytes, *, lease_seconds: float
    ) -> None:
        self._require_checkpoint(data)
        if not 0 < lease_seconds <= 120:
            raise ValueError("The lease is outside its bounded interval.")
        row, now = await self._owned_row(context)
        if row.work_deadline is None:
            raise JobFenceLostError()
        row.checkpoint = data
        row.lease_expires_at = min(now + timedelta(seconds=lease_seconds), row.work_deadline)
        await self._session.flush()

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        if not effect_id or len(effect_id) > 100:
            raise ValueError("An effect requires a bounded stable unit identifier.")
        row, _ = await self._owned_row(context)
        if row.pending_effect is not None:
            raise ConflictError("An earlier effect still has an unknown outcome.")
        row.pending_effect = effect_id
        await self._session.flush()

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        self._require_checkpoint(data)
        row, _ = await self._owned_row(context)
        if row.pending_effect != effect_id:
            raise ConflictError("The confirmation does not match the original pending effect.")
        row.pending_effect = None
        row.checkpoint = data
        await self._session.flush()

    @override
    async def finish(
        self, context: JobAttemptContextDTO, *, status: JobStatus, reason: str | None
    ) -> None:
        row, now = await self._owned_row(context)
        if status in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise ValueError("Finishing requires a terminal execution outcome.")
        if row.pending_effect is not None:
            status, reason = JobStatus.RECOVERY_REQUIRED, "unknown_external_effect"
        await self._complete(row, now, status, reason)

    @override
    async def retire_attempt(
        self, job: JobSnapshotDTO, *, status: JobStatus, reason: str, due_at: datetime
    ) -> None:
        await self._queue_turn()
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(DurableJobRow.id == job.job_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            row is None
            or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING)
            or row.status != job.status.value
            or row.attempt_count != job.attempt
            or row.fence != (job.fence.value if job.fence is not None else None)
        ):
            raise JobFenceLostError()
        now = await self._now()
        current = await self._snapshot(row, now)
        if current.binding != job.binding or current.payload != job.payload:
            raise JobFenceLostError("The observed original work binding changed.")
        if (
            row.status == JobStatus.RUNNING.value
            and row.lease_expires_at is not None
            and row.lease_expires_at > now
        ):
            raise JobFenceLostError("An unexpired owner cannot be retired by another worker.")
        if status is JobStatus.QUEUED:
            if row.pending_effect is not None or row.attempt_count >= 3:
                raise ConflictError("The original remaining work cannot safely retry.")
            await self._end_attempt(row, now, reason)
            row.status, row.reason, row.due_at = status.value, reason, due_at
            row.fence = row.worker_id = row.lease_expires_at = None
            await self._session.flush()
        elif status is not JobStatus.RUNNING:
            await self._complete(row, now, status, reason)
        else:
            raise ValueError("Retirement cannot start an attempt.")

    @override
    async def request_cancel(self, job_id: JobId) -> None:
        self._require_transaction()
        await self._session.execute(
            update(DurableJobRow)
            .where(
                DurableJobRow.id == job_id.value,
                DurableJobRow.binding_kind == "product",
                DurableJobRow.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)),
            )
            .values(cancel_requested=True)
        )

    def _require_transaction(self) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("Job persistence requires its caller-owned transaction.")

    async def _queue_turn(self) -> None:
        """Serialize ordinary queue decisions using the shared queue-row lock."""
        self._require_transaction()
        row = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("The ordinary queue is not initialized.")

    async def _now(self) -> datetime:
        """Use the database clock for lease and attempt decisions."""
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise RuntimeError("The authoritative database clock is unavailable.")
        return now

    async def _owned_row(self, context: JobAttemptContextDTO) -> tuple[DurableJobRow, datetime]:
        """Lock the exact active attempt and reject an expired or superseded claim."""
        self._require_transaction()
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(
                DurableJobRow.id == context.job_id.value,
                DurableJobRow.status == JobStatus.RUNNING.value,
                DurableJobRow.fence == context.fence.value,
                DurableJobRow.attempt_count == context.attempt,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = await self._now()
        if (
            row is None
            or row.lease_expires_at is None
            or row.lease_expires_at <= now
            or row.work_deadline is None
            or row.work_deadline <= now
        ):
            raise JobFenceLostError("The ordinary job attempt no longer owns its lease.")
        saved = await self._snapshot(row, now)
        if saved.binding != context.binding or saved.payload != context.payload:
            raise JobFenceLostError("The attempt does not match its original immutable work.")
        return row, now

    @staticmethod
    def _require_checkpoint(data: bytes) -> None:
        if len(data) > 65536:
            raise ValueError("A job checkpoint may contain at most 64 KiB.")

    async def _end_attempt(self, row: DurableJobRow, now: datetime, reason: str | None) -> None:
        """Record the end of the owned attempt without committing the caller transaction."""
        if row.fence is not None:
            await self._session.execute(
                update(DurableJobAttemptRow)
                .where(
                    DurableJobAttemptRow.job_id == row.id,
                    DurableJobAttemptRow.fence == row.fence,
                    DurableJobAttemptRow.ended_at.is_(None),
                )
                .values(ended_at=now, reason=reason)
            )

    async def _complete(
        self, row: DurableJobRow, now: datetime, status: JobStatus, reason: str | None
    ) -> None:
        """Persist the terminal job outcome with the original operation result."""
        if reason is not None and len(reason) > 100:
            raise ValueError("A job outcome reason must be bounded.")
        binding = (await self._snapshot(row, now)).binding
        await self._end_attempt(row, now, reason)
        row.status, row.reason, row.terminal_at = status.value, reason, now
        row.fence = row.worker_id = row.lease_expires_at = None
        if isinstance(binding, ProductJobBindingDTO):
            retention = update(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == binding.operation_id.value,
                IdempotencyReservationRow.state == OperationReservationState.REPLAYABLE,
                IdempotencyReservationRow.replay_kind == OperationReplayKind.ASYNC_JOB,
            )
            if status is JobStatus.RECOVERY_REQUIRED or row.pending_effect is not None:
                await self._session.execute(retention.values(expires_at=None))
            else:
                await self._session.execute(
                    retention.where(IdempotencyReservationRow.expires_at.is_(None)).values(
                        expires_at=now + timedelta(hours=24)
                    )
                )
        else:
            obligation = await self._session.scalar(
                select(ArtifactCleanupObligationRow)
                .where(ArtifactCleanupObligationRow.id == binding.obligation_id.value)
                .with_for_update()
            )
            if obligation is None or PostgresJobBindingMapper.cleanup(obligation) != binding:
                raise ConflictError("The original cleanup obligation cannot be confirmed.")
            # Execution retirement cannot release physical bytes or change the
            # originating product replay, including an expired business origin.
            obligation.execution_status = status.value
            obligation.execution_reason = reason
        await self._session.flush()

    async def _snapshot(self, row: DurableJobRow, now: datetime) -> JobSnapshotDTO:
        """Reconstruct job state and its original authority from persisted facts."""
        binding: ProductJobBindingDTO | ArtifactCleanupJobBindingDTO
        if row.binding_kind == "product":
            binding = PostgresJobBindingMapper.product(row)
        elif row.binding_kind == "artifact_cleanup" and row.cleanup_obligation_id is not None:
            obligation = await self._session.get(
                ArtifactCleanupObligationRow, row.cleanup_obligation_id
            )
            if obligation is None or any(
                value is not None
                for value in (
                    row.operation_id,
                    row.principal_id,
                    row.principal_kind,
                    row.action_id,
                    row.human_authority,
                    row.human_subject,
                    row.human_version,
                )
            ):
                raise ConflictError("The original cleanup job binding is incomplete.")
            binding = PostgresJobBindingMapper.cleanup(obligation)
            if (row.installation_id, row.organization_id, row.project_id, row.request_id) != (
                binding.scope.installation_id.value,
                binding.scope.organization_id.value,
                binding.scope.project_id.value,
                binding.origin.request_id.value,
            ):
                raise ConflictError("The original cleanup job scope is inconsistent.")
        else:
            raise ConflictError("The original job binding kind is unsupported.")
        return JobSnapshotDTO(
            job_id=JobId(row.id),
            binding=binding,
            payload=JobPayload(row.payload_kind, row.payload_version, row.payload),
            status=JobStatus(row.status),
            admitted_at=row.admitted_at,
            queued_deadline=row.queued_deadline,
            due_at=row.due_at,
            observed_at=now,
            attempt=row.attempt_count,
            work_deadline=row.work_deadline,
            fence=JobFence(row.fence) if row.fence is not None else None,
            lease_expires_at=row.lease_expires_at,
            cancel_requested=row.cancel_requested,
            pending_effect=row.pending_effect,
            reason=row.reason,
            checkpoint=row.checkpoint,
        )
