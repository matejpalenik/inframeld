import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import override

from inframeld_backend.indexing.application.dtos.parsed_pdf_dto import ParsedPdfDTO
from inframeld_backend.indexing.application.protocols.pipeline_pdf_preparation_records import (
    PipelinePdfPreparationRecords,
)
from inframeld_backend.indexing.application.services.sealed_pdf_processing_service import (
    SealedPdfProcessingService,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.pipelines.domain.enums.pipeline_action import PipelineAction
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactIntegrityError
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.artifact_preparation_io import (
    ArtifactPreparationIO,
)
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_handler import JobHandler
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)

_MAX_CANONICAL_BYTES = 32 * 1024**2
_MAX_CODEPOINTS = 10 * 1024**2
_MAX_CHUNKS = 2000
_PARSER_SECONDS = 300
_STREAM_CHUNK_BYTES = 64 * 1024


class PipelinePdfPreparationJobHandler(JobHandler):
    """Prepare one original admitted PDF through the private parser and artifact store."""

    def __init__(
        self,
        records: PipelinePdfPreparationRecords,
        processing: SealedPdfProcessingService,
        preparation_io_factory: Callable[[], ArtifactPreparationIO],
    ) -> None:
        self._records = records
        self._processing = processing
        self._preparation_io_factory = preparation_io_factory

    @override
    def payload_type(self) -> tuple[str, int]:
        return PipelinePdfPreparationInput.KIND, PipelinePdfPreparationInput.VERSION

    @override
    async def run(self, context: JobAttemptContextDTO, checkpoints: JobCheckpoints) -> None:
        binding = context.binding
        if (
            not isinstance(binding, ProductJobBindingDTO)
            or binding.authority.pipeline_id is None
            or binding.authority.action_id.value != PipelineAction.BUILD.value
        ):
            raise JobStoppedError("PDF preparation requires its original Pipeline Build binding.")
        inputs = PipelinePdfPreparationInput.from_payload(context.payload)
        await checkpoints.check(context)
        work = await self._records.load(context, inputs)
        if work is None:
            return

        source, definition = work
        scope = ArtifactScopeDTO(
            binding.authority.installation_id,
            binding.authority.organization_id,
            binding.authority.project_id,
        )
        if source.scope != scope:
            raise ArtifactIntegrityError("The PDF source is outside the original scope.")
        remaining = (context.work_deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise JobStoppedError("The original PDF preparation deadline elapsed.")
        deadline = asyncio.get_running_loop().time() + min(_PARSER_SECONDS, remaining)
        parsed = await self._processing.process(
            source, attempt_id=context.fence.value, definition=definition, deadline=deadline
        )
        self._require_result(context, source, parsed)
        await checkpoints.check(context)
        allocation = await self._records.allocate(
            context, inputs, source, len(parsed.canonical_bytes), len(parsed.chunk_ranges)
        )
        self._require_allocation(allocation, binding, source, len(parsed.canonical_bytes))

        preparation = self._preparation_io_factory()
        async with preparation.hold(allocation):
            sealed = await preparation.stage(allocation, self._stream(parsed.canonical_bytes))
            reservation = allocation.reservation
            if sealed != ArtifactAttemptDTO(
                reservation.artifact_id,
                reservation.attempt_id,
                scope,
                len(parsed.canonical_bytes),
                parsed.canonical_digest,
            ):
                raise ArtifactIntegrityError("Staging did not seal the exact canonical PDF output.")
            observation = await self._records.begin_put(context, inputs, source, allocation, sealed)
            verified = await preparation.verify(sealed, upload=True, observation=observation)
            if verified.attempt != sealed:
                raise ArtifactIntegrityError("Readback did not verify the exact output seal.")

        await self._records.publish(
            context,
            inputs,
            source,
            allocation,
            observation,
            verified,
            self._canonical_identity(scope, inputs, definition, parsed.canonical_digest),
            parsed.chunk_ranges,
        )

    @staticmethod
    def _require_result(
        context: JobAttemptContextDTO, source: ArtifactAttemptDTO, parsed: ParsedPdfDTO
    ) -> None:
        if (
            parsed.attempt_id != context.fence.value
            or parsed.source_digest != source.digest
            or type(parsed.canonical_bytes) is not bytes
            or not 1 <= len(parsed.canonical_bytes) <= _MAX_CANONICAL_BYTES
            or parsed.canonical_digest != ArtifactContentDigest.from_content(parsed.canonical_bytes)
            or not 1 <= len(parsed.chunk_ranges) <= _MAX_CHUNKS
        ):
            raise ArtifactIntegrityError("The PDF output did not match the original parser result.")
        previous_end = 0
        for start, end in parsed.chunk_ranges:
            if (
                type(start) is not int
                or type(end) is not int
                or not previous_end <= start < end <= _MAX_CODEPOINTS
            ):
                raise ArtifactIntegrityError("The PDF output contains invalid chunk ranges.")
            previous_end = end

    @staticmethod
    def _require_allocation(
        allocation: ArtifactAllocationDTO,
        binding: ProductJobBindingDTO,
        source: ArtifactAttemptDTO,
        canonical_size: int,
    ) -> None:
        reservation = allocation.reservation
        cleanup = allocation.cleanup_binding
        if (
            reservation.scope != source.scope
            or cleanup.scope != source.scope
            or cleanup.kind is not ArtifactCleanupKind.ABANDONED_STAGING
            or cleanup.origin
            != BusinessOperationArtifactOriginDTO(binding.operation_id, binding.request_id)
            or reservation.artifact_id == source.artifact_id
            or reservation.attempt_id == source.attempt_id
            or not canonical_size <= reservation.limit_bytes <= _MAX_CANONICAL_BYTES
            or reservation.released
            or reservation.retired
            or reservation.published
        ):
            raise ArtifactIntegrityError(
                "The canonical PDF allocation differs from the original work."
            )

    @staticmethod
    async def _stream(content: bytes) -> AsyncIterator[bytes]:
        for offset in range(0, len(content), _STREAM_CHUNK_BYTES):
            yield content[offset : offset + _STREAM_CHUNK_BYTES]

    @staticmethod
    def _canonical_identity(
        scope: ArtifactScopeDTO,
        inputs: PipelinePdfPreparationInput,
        definition: DoclingProcessingDefinition,
        digest: ArtifactContentDigest,
    ) -> ArtifactContentDigest:
        recipe = (
            b"inframeld-canonical-pdf-identity-v1",
            scope.installation_id.value.bytes,
            scope.organization_id.value.bytes,
            scope.project_id.value.bytes,
            inputs.source.version_id.value.bytes,
            b"inframeld-pdf-canonical-v1",
            definition.docling_slim_version.encode("ascii"),
            definition.docling_core_version.encode("ascii"),
            bytes.fromhex(definition.asset_manifest_sha256),
            b"text-native-ocr-disabled",
            digest.value,
        )
        return ArtifactContentDigest.from_content(
            b"".join(len(part).to_bytes(4, "big") + part for part in recipe)
        )
