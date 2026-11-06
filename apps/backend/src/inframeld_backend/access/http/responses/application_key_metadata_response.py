from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.application_key_prefix import ApplicationKeyPrefix


class ApplicationKeyMetadataResponse(BaseModel):
    key_id: UUID = Field(serialization_alias="keyId")
    application_principal_id: UUID = Field(serialization_alias="applicationPrincipalId")
    project_id: UUID = Field(serialization_alias="projectId")
    prefix: Literal[ApplicationKeyPrefix.APPLICATION]
    allowed_adapters: tuple[ApplicationKeyAdapter, ...] = Field(
        serialization_alias="allowedAdapters", min_length=1, max_length=2
    )
    created_at: datetime = Field(serialization_alias="createdAt")
    expires_at: datetime = Field(serialization_alias="expiresAt")
    revoked_at: datetime | None = Field(serialization_alias="revokedAt")
