from datetime import datetime

from pydantic import Field

from inframeld_backend.access.http.responses.project_metadata_response import (
    ProjectMetadataResponse,
)


class ProjectMetadataChangeResponse(ProjectMetadataResponse):
    operation_id: str = Field(
        serialization_alias="operationId",
        description="Original operation identity for safe recovery.",
    )
    idempotency_expires_at: datetime = Field(
        serialization_alias="idempotencyExpiresAt",
        description="Original replay deadline, unchanged by retries.",
    )
