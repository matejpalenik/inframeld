import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_scope_lock import (
    PostgresProjectScopeLock,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.writers.postgres_artifact_cleanup_audit_writer import (
    PostgresArtifactCleanupAuditWriter,
)
from inframeld_backend.indexing.application.protocols.pipeline_pdf_preparation_records import (
    PipelinePdfPreparationRecords,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.infrastructure.readers.postgres_admitted_pdf_source_reader import (
    PostgresAdmittedPdfSourceReader,
)
from inframeld_backend.indexing.infrastructure.readers.postgres_processing_profile_use_reader import (
    PostgresProcessingProfileUseReader,
)
from inframeld_backend.indexing.infrastructure.rows.parsed_pdf_chunk_row import ParsedPdfChunkRow
from inframeld_backend.indexing.infrastructure.rows.parsed_pdf_generation_row import (
    ParsedPdfGenerationRow,
)
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.pipelines.domain.enums.pipeline_action import PipelineAction
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactCapacityError
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.artifact_capacity_reader import (
    ArtifactCapacityReader,
)
from inframeld_backend.shared.application.services.artifact_allocation_service import (
    ArtifactAllocationService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_admission_service import (
    ArtifactCleanupAdmissionService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_cleanup_obligation_repository import (
    PostgresArtifactCleanupObligationRepository,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.writers.postgres_artifact_cleanup_admission_writer import (
    PostgresArtifactCleanupAdmissionWriter,
)

_PUT_UNIT = "publish-canonical-pdf"
_MAX_CHUNKS = 2000


class PostgresPipelinePdfPreparationRecords(PipelinePdfPreparationRecords):
    """Close each guarded transaction before parsing, private staging or remote I/O."""

    def __init__(
        self, database: Database, capacity: ArtifactCapacityReader, *, database_seconds: float
    ) -> None:
        self._database = database
        self._capacity = capacity
        self._database_seconds = database_seconds

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[AsyncSession]:
        try:
            async with (
                asyncio.timeout(self._database_seconds),
                self._database.session() as session,
                session.begin(),
            ):
                yield session
        except (TimeoutError, InterfaceError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError(
                "PDF preparation state could not be confirmed."
            ) from None

    @staticmethod
    def _binding(
        context: JobAttemptContextDTO, inputs: PipelinePdfPreparationInput
    ) -> ProductJobBindingDTO:
        binding = context.binding
        if (
            not isinstance(binding, ProductJobBindingDTO)
            or binding.authority.pipeline_id is None
            or binding.authority.action_id.value != PipelineAction.BUILD.value
            or inputs.to_payload() != context.payload
        ):
            raise ConflictError("PDF preparation requires the exact original Build binding.")
        return binding

    @staticmethod
    async def check_source(
        session: AsyncSession,
        binding: ProductJobBindingDTO,
        inputs: PipelinePdfPreparationInput,
        *,
        for_publication: bool,
    ) -> tuple[ArtifactAttemptDTO, DoclingProcessingDefinition]:
        authority = binding.authority
        await AdmittedWorkAuthorizationService(
            PostgresAdmittedWorkFactsReader(session)
        ).require_current(authority)
        source = await PostgresAdmittedPdfSourceReader(session).read(
            authority, inputs.source, for_publication=for_publication
        )
        definition = await PostgresProcessingProfileUseReader(session).read(
            authority, inputs.processing_profile_id
        )
        return source, definition

    @staticmethod
    async def _require_current(
        jobs: PostgresJobStore, context: JobAttemptContextDTO
    ) -> JobSnapshotDTO:
        current = await jobs.require_current(context)
        if current.cancel_requested:
            raise JobStoppedError("PDF preparation was canceled.")
        if current.work_deadline != context.work_deadline:
            raise JobStoppedError("PDF preparation's original work deadline changed.")
        return current

    @override
    async def load(
        self, context: JobAttemptContextDTO, inputs: PipelinePdfPreparationInput
    ) -> tuple[ArtifactAttemptDTO, DoclingProcessingDefinition] | None:
        binding = self._binding(context, inputs)
        async with self._transaction() as session:
            source, definition = await self.check_source(
                session, binding, inputs, for_publication=False
            )
            current = await self._require_current(PostgresJobStore(session), context)
            if current.pending_effect is not None:
                raise ConflictError("An original PDF publication effect is unresolved.")
            output = await session.get(ParsedPdfGenerationRow, context.job_id.value)
            if output is None and not current.checkpoint:
                return source, definition
            if output is None or (
                output.installation_id,
                output.organization_id,
                output.project_id,
                output.document_id,
                output.document_version_id,
                output.processing_profile_id,
            ) != (
                source.scope.installation_id.value,
                source.scope.organization_id.value,
                source.scope.project_id.value,
                inputs.source.document_id.value,
                inputs.source.version_id.value,
                inputs.processing_profile_id.value,
            ):
                raise ConflictError("The retained PDF generation does not match its Build.")
            attempt = await session.get(ArtifactAttemptRow, output.canonical_artifact_attempt_id)
            count = await session.scalar(
                select(func.count())
                .select_from(ParsedPdfChunkRow)
                .where(ParsedPdfChunkRow.generation_id == output.id)
            )
            if (
                attempt is None
                or not attempt.published
                or not attempt.put_confirmed
                or attempt.retired
                or attempt.remote_removed
                or count is None
                or not 1 <= count <= _MAX_CHUNKS
                or current.checkpoint
                != self._checkpoint(ArtifactAttemptId(attempt.id), output.canonical_identity, count)
            ):
                raise ConflictError("The retained PDF publication could not be confirmed.")
            return None

    @override
    async def allocate(
        self,
        context: JobAttemptContextDTO,
        inputs: PipelinePdfPreparationInput,
        source: ArtifactAttemptDTO,
        canonical_size: int,
        chunk_count: int,
    ) -> ArtifactAllocationDTO:
        binding = self._binding(context, inputs)
        authority = binding.authority
        credential = authority.human_binding
        if credential is None:
            raise AccessDeniedError()
        async with self._transaction() as session:
            # The existing artifact allocator needs the exclusive Project turn.
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=authority.installation_id, identity=credential.identity
            )
            organization = await PostgresProjectScopeLock.acquire(
                session, authority.principal_id, authority.project_id, shared=False
            )
            if organization != authority.organization_id.value:
                raise AccessDeniedError()
            await self._require_source(session, binding, inputs, source)
            jobs = PostgresJobStore(session)
            await jobs.lock_queue()
            current = await self._require_current(jobs, context)
            if current.pending_effect is not None or current.checkpoint:
                raise ConflictError("The Build already has output or an unresolved effect.")
            await self._require_chunk_capacity(session, chunk_count)
            return await ArtifactAllocationService(
                SqlAlchemyTransactionManager(session),
                PostgresArtifactAttemptRepository(session),
                PostgresArtifactCleanupObligationRepository(session),
                ArtifactCleanupAdmissionService(
                    PostgresArtifactCleanupAdmissionWriter(session),
                    PostgresArtifactCleanupAuditWriter(session),
                ),
                self._capacity,
            ).allocate_in_transaction(
                scope=source.scope,
                artifact_id=ArtifactId(context.job_id.value),
                attempt_id=ArtifactAttemptId(uuid5(context.fence.value, "canonical-attempt")),
                reservation_id=ArtifactStagingReservationId(
                    uuid5(context.fence.value, "canonical-reservation")
                ),
                obligation_id=ArtifactCleanupObligationId(
                    uuid5(context.fence.value, "canonical-cleanup")
                ),
                origin=BusinessOperationArtifactOriginDTO(binding.operation_id, binding.request_id),
                limit_bytes=canonical_size,
            )

    @override
    async def begin_put(
        self,
        context: JobAttemptContextDTO,
        inputs: PipelinePdfPreparationInput,
        source: ArtifactAttemptDTO,
        allocation: ArtifactAllocationDTO,
        sealed: ArtifactAttemptDTO,
    ) -> JobEffectId:
        binding = self._binding(context, inputs)
        async with self._transaction() as session:
            await self._require_source(session, binding, inputs, source)
            jobs = PostgresJobStore(session)
            current = await self._require_current(jobs, context)
            if current.pending_effect is not None or current.checkpoint:
                raise ConflictError("PDF preparation cannot start a replacement PUT.")
            self._require_allocation(context, source, allocation, sealed)
            attempts = PostgresArtifactAttemptRepository(session)
            await attempts.seal(allocation, sealed)
            if not await attempts.begin_put(allocation, sealed):
                raise ConflictError("The original canonical PUT has already begun.")
            observation = JobEffectId(uuid5(context.fence.value, "canonical-put"))
            await jobs.register_effect(
                JobEffectBindingDTO(
                    observation,
                    context,
                    _PUT_UNIT,
                    JobEffectAction.PUT,
                    sealed.artifact_id,
                    sealed.attempt_id,
                    sealed.scope,
                    sealed.length,
                    sealed.digest,
                )
            )
            return observation

    @override
    async def publish(
        self,
        context: JobAttemptContextDTO,
        inputs: PipelinePdfPreparationInput,
        source: ArtifactAttemptDTO,
        allocation: ArtifactAllocationDTO,
        observation: JobEffectId,
        verified: VerifiedArtifactDTO,
        canonical_identity: ArtifactContentDigest,
        chunk_ranges: tuple[tuple[int, int], ...],
    ) -> None:
        binding = self._binding(context, inputs)
        output = verified.attempt
        self._require_allocation(context, source, allocation, output)
        async with self._transaction() as session:
            await self._require_source(session, binding, inputs, source)
            jobs = PostgresJobStore(session)
            await jobs.lock_queue()
            current = await self._require_current(jobs, context)
            effect = await jobs.effect(observation)
            if (
                current.pending_effect != _PUT_UNIT
                or current.checkpoint
                or effect is None
                or effect.admitted_at is None
                or effect.aborted_at is not None
                or effect.consumed_at is not None
                or effect.binding
                != JobEffectBindingDTO(
                    observation,
                    context,
                    _PUT_UNIT,
                    JobEffectAction.PUT,
                    output.artifact_id,
                    output.attempt_id,
                    output.scope,
                    output.length,
                    output.digest,
                )
            ):
                raise ConflictError("Verified output cannot be bound to the original PDF PUT.")
            await self._require_chunk_capacity(session, len(chunk_ranges))
            attempts = PostgresArtifactAttemptRepository(session)
            await attempts.confirm_verified(allocation, verified)
            await attempts.publish_verified(allocation, verified)
            session.add(
                ParsedPdfGenerationRow(
                    id=context.job_id.value,
                    installation_id=source.scope.installation_id.value,
                    organization_id=source.scope.organization_id.value,
                    project_id=source.scope.project_id.value,
                    document_id=inputs.source.document_id.value,
                    document_version_id=inputs.source.version_id.value,
                    processing_profile_id=inputs.processing_profile_id.value,
                    canonical_artifact_attempt_id=output.attempt_id.value,
                    canonical_identity=canonical_identity.value,
                )
            )
            await session.flush()
            session.add_all(
                ParsedPdfChunkRow(
                    generation_id=context.job_id.value,
                    ordinal=ordinal,
                    start_codepoint=start,
                    end_codepoint=end,
                )
                for ordinal, (start, end) in enumerate(chunk_ranges)
            )
            await jobs.confirm_effect(
                context,
                _PUT_UNIT,
                self._checkpoint(output.attempt_id, canonical_identity.value, len(chunk_ranges)),
            )

    @classmethod
    async def _require_source(
        cls,
        session: AsyncSession,
        binding: ProductJobBindingDTO,
        inputs: PipelinePdfPreparationInput,
        expected: ArtifactAttemptDTO,
    ) -> None:
        actual, _ = await cls.check_source(session, binding, inputs, for_publication=True)
        if actual != expected:
            raise ConflictError("The original PDF source seal changed.")

    @staticmethod
    def _require_allocation(
        context: JobAttemptContextDTO,
        source: ArtifactAttemptDTO,
        allocation: ArtifactAllocationDTO,
        attempt: ArtifactAttemptDTO,
    ) -> None:
        original = allocation.reservation
        if (
            original.scope != source.scope
            or attempt.scope != original.scope
            or original.artifact_id != ArtifactId(context.job_id.value)
            or attempt.artifact_id != original.artifact_id
            or attempt.attempt_id != original.attempt_id
            or attempt.length != original.limit_bytes
        ):
            raise ConflictError("Canonical bytes do not match their reserved original scope.")

    @staticmethod
    async def _require_chunk_capacity(session: AsyncSession, addition: int) -> None:
        # Until expiry owns removal, all retained ranges count conservatively.
        count = await session.scalar(select(func.count()).select_from(ParsedPdfChunkRow))
        if count is None or not 1 <= addition <= _MAX_CHUNKS - count:
            raise ArtifactCapacityError("The installation has no safe chunk capacity.")

    @staticmethod
    def _checkpoint(attempt: ArtifactAttemptId, identity: bytes, count: int) -> bytes:
        return attempt.value.bytes + identity + count.to_bytes(4, "big")
