from abc import abstractmethod
from typing import Protocol

from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId


class PipelinePdfPreparationRecords(Protocol):
    """Own short, current-authority transactions for the original PDF job."""

    @abstractmethod
    async def load(
        self, context: JobAttemptContextDTO, inputs: PipelinePdfPreparationInput
    ) -> tuple[ArtifactAttemptDTO, DoclingProcessingDefinition] | None:
        """Load the exact live source and definition, or prove completed original publication."""
        ...

    @abstractmethod
    async def allocate(
        self,
        context: JobAttemptContextDTO,
        inputs: PipelinePdfPreparationInput,
        source: ArtifactAttemptDTO,
        canonical_size: int,
        chunk_count: int,
    ) -> ArtifactAllocationDTO:
        """Commit original capacity, private staging and cleanup before creating bytes."""
        ...

    @abstractmethod
    async def begin_put(
        self,
        context: JobAttemptContextDTO,
        inputs: PipelinePdfPreparationInput,
        source: ArtifactAttemptDTO,
        allocation: ArtifactAllocationDTO,
        sealed: ArtifactAttemptDTO,
    ) -> JobEffectId:
        """Commit the seal and first physical invocation admission intent."""
        ...

    @abstractmethod
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
        """Publish the verified artifact, ordered chunks and exact checkpoint atomically."""
        ...
