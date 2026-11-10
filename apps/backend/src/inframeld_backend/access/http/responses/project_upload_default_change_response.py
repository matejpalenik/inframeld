from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectUploadDefaultChangeResponse(BaseModel):
    """Retain the original resulting audience without disclosing its before snapshot."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    project_id: UUID = Field(
        serialization_alias="projectId",
        description="Exact Project whose saved future-upload audience is represented.",
    )
    access_revision: int = Field(
        serialization_alias="accessRevision",
        description="Project Access revision of this current read or immutable original result.",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    group_ids: list[UUID] = Field(
        serialization_alias="groupIds",
        min_length=1,
        description="Original resulting audience. A later GET may show a different current default.",
    )
    operation_id: str = Field(
        serialization_alias="operationId",
        description="Original operation identity, retained across exact-request recovery.",
    )
    idempotency_expires_at: datetime = Field(
        serialization_alias="idempotencyExpiresAt",
        description="Original replay deadline, unchanged by recovery.",
    )
