from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectMetadataResponse(BaseModel):
    project_id: UUID = Field(
        serialization_alias="projectId",
        description="Permanent Project identity, preserved through rename.",
    )
    organization_id: UUID = Field(
        serialization_alias="organizationId", description="Owning installation Organization."
    )
    name: str | None = Field(
        description="Exact current selector, or null until explicitly allocated."
    )
    display_name: str = Field(
        serialization_alias="displayName",
        description="Stored presentation label, including retained legacy values.",
    )
    metadata_revision: int = Field(
        serialization_alias="metadataRevision",
        description="Review revision for metadata changes, separate from permission revision.",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
