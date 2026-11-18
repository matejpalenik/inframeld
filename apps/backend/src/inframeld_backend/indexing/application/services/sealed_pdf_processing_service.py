import asyncio
from contextlib import aclosing
from uuid import UUID

from inframeld_backend.indexing.application.dtos.parsed_pdf_dto import ParsedPdfDTO
from inframeld_backend.indexing.application.errors.pdf_parse_error import PdfParseError
from inframeld_backend.indexing.application.protocols.pdf_parser import PdfParser
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
    ArtifactStoreUnavailableError,
)
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)

_MAX_PDF_BYTES = 25 * 1024**2
_MAX_ATTEMPT_SECONDS = 300
_DEADLINE_ELAPSED = "The PDF processing deadline elapsed."
_SOURCE_MISMATCH = "The PDF source did not match its sealed expectation."


class SealedPdfProcessingService:
    """Read and process an exact PDF seal supplied by its authorized worker owner."""

    def __init__(self, artifact_store: ArtifactStore, parser: PdfParser) -> None:
        self._artifact_store = artifact_store
        self._parser = parser

    async def process(
        self,
        source: ArtifactAttemptDTO,
        *,
        attempt_id: UUID,
        definition: DoclingProcessingDefinition,
        deadline: float,
    ) -> ParsedPdfDTO:
        """Verify exact source bytes before dispatch within the caller's original deadline.

        The caller checks source and profile authority and owns output publication.
        Cleanup evidence refers to this attempt's parser process.
        """
        loop = asyncio.get_running_loop()
        if not 0 < deadline - loop.time() <= _MAX_ATTEMPT_SECONDS:
            raise PdfParseError("The PDF processing deadline is invalid.", cleanup_confirmed=True)
        if type(source.length) is not int or not 1 <= source.length <= _MAX_PDF_BYTES:
            raise PdfParseError("The PDF source seal is outside its bound.", cleanup_confirmed=True)

        dispatched = False
        try:
            async with asyncio.timeout_at(deadline):
                content = await self._read_source(source)
                if loop.time() >= deadline:
                    raise TimeoutError
                dispatched = True
                result = await self._parser.parse(
                    content,
                    attempt_id=attempt_id,
                    source_digest=source.digest,
                    definition=definition,
                    deadline=deadline,
                )
                if loop.time() >= deadline:
                    raise PdfParseError(_DEADLINE_ELAPSED, cleanup_confirmed=True)
                return result
        except TimeoutError:
            raise PdfParseError(_DEADLINE_ELAPSED, cleanup_confirmed=not dispatched) from None

    async def _read_source(self, source: ArtifactAttemptDTO) -> bytes:
        content = bytearray()
        try:
            async with aclosing(self._artifact_store.read(source)) as stream:
                async for chunk in stream:
                    if type(chunk) is not bytes or len(chunk) > source.length - len(content):
                        raise PdfParseError(_SOURCE_MISMATCH, cleanup_confirmed=True)
                    content.extend(chunk)
        except (
            ArtifactCapacityError,
            ArtifactIntegrityError,
            ArtifactStoreUnavailableError,
            OSError,
        ):
            raise PdfParseError(
                "The sealed PDF source could not be read.", cleanup_confirmed=True
            ) from None

        captured = bytes(content)
        if (
            len(captured) != source.length
            or ArtifactContentDigest.from_content(captured) != source.digest
        ):
            raise PdfParseError(_SOURCE_MISMATCH, cleanup_confirmed=True)
        return captured
