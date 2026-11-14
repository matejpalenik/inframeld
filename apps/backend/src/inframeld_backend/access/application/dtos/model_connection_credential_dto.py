from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


@dataclass(frozen=True, slots=True)
class ModelConnectionCredentialDTO:
    """Safe slot metadata. A never-written slot has no credential ID or timestamp."""

    project_id: ProjectId
    connection_id: ModelConnectionId
    credential_id: UUID | None
    revision: int
    present: bool
    changed_at: datetime | None
