from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO


class PipelinePdfPreparationFactsReader(Protocol):
    """Read exact no-target preparation facts in the original admission transaction."""

    async def authorize(
        self, *, access: AccessContextDTO, project_id: ProjectId, pipeline_id: PipelineId
    ) -> ArtifactScopeDTO: ...

    async def read_reviewed(
        self,
        *,
        access: AccessContextDTO,
        scope: ArtifactScopeDTO,
        pipeline_id: PipelineId,
        configuration_revision: int,
        collection_revision_id: CollectionRevisionId,
    ) -> PipelinePdfPreparationInput: ...
