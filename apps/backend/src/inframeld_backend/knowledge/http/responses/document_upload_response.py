from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    operation_id: str = Field(serialization_alias="operationId")
    project_id: UUID = Field(serialization_alias="projectId")
    document_id: UUID = Field(serialization_alias="documentId")
    version_id: UUID = Field(serialization_alias="documentVersionId")
    idempotency_expires_at: datetime | None = Field(serialization_alias="idempotencyExpiresAt")
