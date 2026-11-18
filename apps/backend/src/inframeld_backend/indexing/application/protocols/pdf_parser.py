from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.indexing.application.dtos.parsed_pdf_dto import ParsedPdfDTO
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)


class PdfParser(Protocol):
    """Convert one authorized, sealed PDF with the full saved processing definition."""

    @abstractmethod
    async def parse(
        self,
        source: bytes,
        *,
        attempt_id: UUID,
        source_digest: ArtifactContentDigest,
        definition: DoclingProcessingDefinition,
        deadline: float,
    ) -> ParsedPdfDTO:
        """Use one absolute event-loop deadline and return independently checked output.

        The caller owns authorization, artifact reads and publication. Cancellation
        never turns an unknown attempt outcome into a usable result.
        """
        ...
