from dataclasses import dataclass
from typing import Literal

from inframeld_backend.pipelines.application.dtos.saved_pipeline_dto import SavedPipelineDTO
from inframeld_backend.pipelines.domain.enums.pipeline_action import PipelineAction
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineCreationDTO:
    """Preserve the initial revision, grants and Project revision on exact replay."""

    pipeline: SavedPipelineDTO
    operation_id: OperationId
    project_access_revision: int
    initial_actions: tuple[PipelineAction, ...]
    can_grant: Literal[True] = True
