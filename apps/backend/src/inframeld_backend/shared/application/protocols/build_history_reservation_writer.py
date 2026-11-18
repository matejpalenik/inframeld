from abc import abstractmethod
from typing import Protocol

from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class BuildHistoryReservationWriter(Protocol):
    """Reserve mandatory Build history inside its owning admission transaction."""

    @abstractmethod
    async def reserve_build(
        self, *, scope: ArtifactScopeDTO, operation_id: OperationId, pipeline_id: PipelineId
    ) -> None:
        """Charge an authorized, exact original before queue admission."""
        ...
