from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


@dataclass(frozen=True, slots=True)
class ModelSelectionDTO:
    """Scope an exact model alias to its Project, connection and role."""

    project_id: ProjectId
    connection_id: ModelConnectionId
    model: str
    role: ModelRole

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("A model selection requires an exact model.")
